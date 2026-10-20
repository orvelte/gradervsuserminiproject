#!/usr/bin/env python3
"""Self-hosted vLLM for Qwen3.8-27B on a RunPod GPU pod (an alternative to internals/modal/vllm_server.py).

    python internals/runpod/pod.py create [--gpu "NVIDIA H100 PCIe"] [--count 1]   # PAID from creation until stop/terminate
    python internals/runpod/pod.py status
    python internals/runpod/pod.py wait                 # until /v1/models answers (cold start: download + load)
    python internals/runpod/pod.py stop                 # stops billing for the GPU (the volume is kept, small cost)
    python internals/runpod/pod.py terminate            # deletes the pod and its volume

Needs RUNPOD_API_KEY in .env (never printed). The vLLM API key is VLLM_API_KEY from .env, passed to the pod. On
`create`, VLLM_BASE_URL in .env is set to the pod's proxy URL (https://<pod-id>-8000.proxy.runpod.net/v1), so the
`vllm_completions` provider and internals/vllm_smoke.py use it with no other change. The pod id is kept in
internals/runpod/.pod_id (gitignored). Weights cache on the pod volume (/workspace/hf), so a stopped-then-started pod
skips the 55 GB download.
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from dotenv import dotenv_values

REPO = Path(__file__).resolve().parents[2]
ENV = REPO / ".env"
POD_FILE = Path(__file__).resolve().parent / ".pod_id"
API = "https://rest.runpod.io/v1"
MODEL = "Qwen/Qwen3.8-27B"
VLLM_IMAGE = "vllm/vllm-openai:v0.32.0"     # same vLLM version as the Modal server


def _key(name: str) -> str:
    v = dotenv_values(ENV).get(name)
    if not v:
        sys.exit(f"{name} is missing from .env")
    return v


def _req(method: str, path: str, body: dict | None = None):
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Authorization": f"Bearer {_key('RUNPOD_API_KEY')}", "Content-Type": "application/json",
                                          "User-Agent": "gradervsuser-internals/1.0"})   # Cloudflare 403/1010 on Python-urllib
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            txt = r.read().decode()
            return json.loads(txt) if txt.strip() else {}
    except urllib.error.HTTPError as e:
        sys.exit(f"RunPod API {method} {path}: HTTP {e.code} {e.read().decode()[:400]}")


def _set_env(name: str, value: str) -> None:
    lines = ENV.read_text().splitlines()
    lines = [l for l in lines if not l.startswith(f"{name}=")] + [f"{name}={value}"]
    ENV.write_text("\n".join(lines) + "\n")


def create(gpu: str, count: int) -> None:
    if POD_FILE.exists():
        sys.exit(f"a pod is already recorded ({POD_FILE.read_text().strip()}); stop/terminate it first")
    args = [MODEL, "--served-model-name", "qwen3.8-27b", "--host", "0.0.0.0", "--port", "8000", "--api-key", _key("VLLM_API_KEY"),
            "--max-model-len", "131072", "--gpu-memory-utilization", "0.92", "--limit-mm-per-prompt", '{"image": 0, "video": 0}',
            "--enable-prefix-caching", "--max-num-seqs", "24", "--tensor-parallel-size", str(count)]
    body = {"name": "qwen38-vllm", "imageName": VLLM_IMAGE, "gpuTypeIds": [gpu], "gpuCount": count, "cloudType": "SECURE",
            "computeType": "GPU", "containerDiskInGb": 40, "volumeInGb": 120, "volumeMountPath": "/workspace", "ports": ["8000/tcp"],   # not 8000/http: the proxy times out at ~100 s (HTTP 524)
            "env": {"HF_HOME": "/workspace/hf", "HF_HUB_ENABLE_HF_TRANSFER": "1"},
            "dockerEntrypoint": ["vllm", "serve"], "dockerStartCmd": args}
    pod = _req("POST", "/pods", body)
    pid = pod.get("id") or sys.exit(f"no pod id in response: {str(pod)[:300]}")
    POD_FILE.write_text(pid)
    _set_env("VLLM_BASE_URL", f"https://{pid}-8000.proxy.runpod.net/v1")
    print(f"created pod {pid} on {count} × {gpu}; VLLM_BASE_URL set in .env; cost/hr: {pod.get('costPerHr')}")


def _pid() -> str:
    return POD_FILE.read_text().strip() if POD_FILE.exists() else sys.exit("no pod recorded")


def status() -> dict:
    p = _req("GET", f"/pods/{_pid()}")
    keep = {k: p.get(k) for k in ("id", "desiredStatus", "lastStatusChange", "costPerHr", "gpu", "machine") if k in p}
    print(json.dumps(keep, indent=1, default=str)[:800])
    return p


def wait(limit_min: int = 40) -> int:
    url = dotenv_values(ENV).get("VLLM_BASE_URL", "").rstrip("/") + "/models"
    t0 = time.time()
    while time.time() - t0 < limit_min * 60:
        try:
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {_key('VLLM_API_KEY')}", "User-Agent": "gradervsuser-internals/1.0"})
            with urllib.request.urlopen(req, timeout=20) as r:
                if r.status == 200:
                    print(f"server ready after {(time.time() - t0) / 60:.1f} min"); return 0
        except Exception:
            pass
        time.sleep(20)
    print(f"not ready after {limit_min} min: check the pod logs in the RunPod console"); return 1


def tcp() -> None:
    """Expose vLLM on a direct TCP port instead of the HTTP proxy. RunPod's proxy (Cloudflare) cuts requests off at
    ~100 s with HTTP 524, and Qwen3.8 turns that reason for minutes exceed it (V1 resume, 2026-10-20). Restarts the
    container; the weights stay on the volume. Sets VLLM_BASE_URL to http://<public ip>:<mapped port>/v1."""
    _req("PATCH", f"/pods/{_pid()}", {"ports": ["8000/tcp"]})
    for _ in range(90):
        p = _req("GET", f"/pods/{_pid()}")
        ip, pm = p.get("publicIp"), (p.get("portMappings") or {})
        port = pm.get("8000") or pm.get(8000)
        if ip and port:
            _set_env("VLLM_BASE_URL", f"http://{ip}:{port}/v1"); print(f"TCP endpoint set in .env (port {port})"); return
        time.sleep(10)
    sys.exit("pod did not report a public IP / TCP port mapping")


def stop() -> None:
    _req("POST", f"/pods/{_pid()}/stop"); print("stop requested (GPU billing ends; volume kept)")


def terminate() -> None:
    _req("DELETE", f"/pods/{_pid()}"); POD_FILE.unlink(missing_ok=True); print("pod terminated")


if __name__ == "__main__":
    a = sys.argv[1:]
    cmd = a[0] if a else "status"
    if cmd == "create":
        gpu = a[a.index("--gpu") + 1] if "--gpu" in a else "NVIDIA H100 PCIe"
        create(gpu, int(a[a.index("--count") + 1]) if "--count" in a else 1)
    elif cmd == "status":
        status()
    elif cmd == "wait":
        sys.exit(wait())
    elif cmd == "tcp":
        tcp()
    elif cmd == "stop":
        stop()
    elif cmd == "terminate":
        terminate()
    else:
        sys.exit(__doc__)
