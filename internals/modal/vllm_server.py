"""Self-hosted vLLM server for Qwen3.8-27B on Modal (assistantaxis.md guardrail 1: generate with vLLM).

    modal deploy internals/modal/vllm_server.py      # PAID while running: one H100 (scales to zero when idle)
    modal app stop qwen38-vllm                        # stop it

Serves the OpenAI-compatible API at https://<workspace>--qwen38-vllm-serve.modal.run/v1 (the URL `modal deploy`
prints). The harness reaches it through the `vllm_completions` provider with VLLM_BASE_URL / VLLM_API_KEY in .env.
The API key lives in the Modal secret `qwen38-vllm-key` (key VLLM_API_KEY); it is never printed or committed.
Weights cache in the Modal volume `hf-cache` so later starts skip the 55 GB download.
To verify on the first deploy (vLLM and the qwen3_5 architecture are newer than this code's author): that the server
starts with these flags, and that /v1/completions honours `return_token_ids` (prompt_token_ids + token_ids in the
response); internals/vllm_smoke.py checks both.
"""
import os
import subprocess

import modal

MODEL = "Qwen/Qwen3.8-27B"
SERVED_NAME = "qwen3.8-27b"
VLLM_VERSION = "0.32.0"

# CUDA devel base: FlashInfer JIT-compiles kernels at engine start and needs nvcc (a debian_slim image failed with
# "Could not find nvcc", 2026-10-20).
image = (modal.Image.from_registry("nvidia/cuda:12.8.1-devel-ubuntu24.04", add_python="3.12")
         .entrypoint([])
         .pip_install(f"vllm=={VLLM_VERSION}", "huggingface_hub[hf_transfer]")
         .env({"HF_HUB_ENABLE_HF_TRANSFER": "1", "VLLM_USE_V1": "1", "CUDA_HOME": "/usr/local/cuda"}))
hf_cache = modal.Volume.from_name("hf-cache", create_if_missing=True)
vllm_cache = modal.Volume.from_name("vllm-cache", create_if_missing=True)
app = modal.App("qwen38-vllm")


@app.function(image=image, gpu="H100", timeout=24 * 3600, scaledown_window=15 * 60,
              volumes={"/root/.cache/huggingface": hf_cache, "/root/.cache/vllm": vllm_cache},
              secrets=[modal.Secret.from_name("qwen38-vllm-key")])
@modal.concurrent(max_inputs=48)
@modal.web_server(port=8000, startup_timeout=30 * 60)
def serve():
    cmd = ["vllm", "serve", MODEL, "--served-model-name", SERVED_NAME, "--host", "0.0.0.0", "--port", "8000",
           "--api-key", os.environ["VLLM_API_KEY"], "--max-model-len", "131072", "--gpu-memory-utilization", "0.92",
           "--limit-mm-per-prompt", '{"image": 0, "video": 0}', "--enable-prefix-caching", "--max-num-seqs", "48"]
    subprocess.Popen(cmd)
