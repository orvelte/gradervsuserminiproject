"""Raw-completions provider for GPT-OSS-120B on Fireworks with mid-reasoning prefill (RS1).

Renders the harness's chat messages with resampling/harmony.py (Harmony format, source-endpoint conventions), samples
from Fireworks' completions endpoint with `raw_output` so special tokens come back verbatim, and parses the
completion into the harness's assistant-message shape. A pending prefill (partial analysis text) is appended after
`<|start|>assistant<|channel|>analysis<|message|>` for exactly one turn; the stored message's reasoning is
prefill + continuation, and the message records `rs_prefill_chars` so the inherited part can be marked later.

Every call prints a `[provider-usage]` line (same shape as the harness providers) with prompt, cached and
completion tokens and the list-price cost, and appends to /opt/output/final/usage.jsonl.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

import harmony as H
from agent_interp_envs.providers.base import BaseProvider
from agent_interp_envs.types import LLMResponse, ToolCall

FIREWORKS_URL = "https://api.fireworks.ai/inference/v1/completions"
MODEL = "accounts/fireworks/models/gpt-oss-120b"
PRICE_IN, PRICE_CACHED, PRICE_OUT = 0.15e-6, 0.15e-6, 0.60e-6  # USD/token, Fireworks list prices (cached billed as prompt unless stated)
MAX_COMPLETION = 32768


class FireworksHarmonyProvider(BaseProvider):
    def __init__(self, model: str, messages: list[dict], tools: list[dict], temperature=None, top_p=None, reasoning_effort="high",
                 conversation_date: str | None = None, usage_log: Path | None = None, **_):
        self.model = model or MODEL
        self.messages = messages
        self.tools = tools
        self.effort = reasoning_effort or "high"
        self.date = conversation_date
        self.temperature, self.top_p = temperature, top_p
        self.prefill: str | None = None
        self.usage_log = usage_log
        self.calls = 0
        self.api_key = os.environ.get("FIREWORKS_API_KEY") or ""
        if not self.api_key:
            raise RuntimeError("FIREWORKS_API_KEY missing")

    # -- prefill -------------------------------------------------------------------------------------------
    def set_prefill(self, text: str) -> None:
        self.prefill = text

    # -- sampling ------------------------------------------------------------------------------------------
    def _request(self, prompt_tokens: list[int]) -> dict:
        body = {"model": self.model, "prompt": H.ENC.decode(prompt_tokens), "max_tokens": MAX_COMPLETION, "raw_output": True}
        if self.temperature is not None:
            body["temperature"] = self.temperature
        if self.top_p is not None:
            body["top_p"] = self.top_p
        last = None
        for attempt in range(8):
            try:
                r = requests.post(FIREWORKS_URL, json=body, headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}, timeout=600)
                if r.status_code == 200:
                    d = r.json()
                    if d.get("choices"):
                        return d
                    last = f"no choices: {str(d)[:200]}"
                elif r.status_code in (429, 500, 502, 503, 504):
                    last = f"HTTP {r.status_code}: {r.text[:200]}"
                else:
                    raise RuntimeError(f"Fireworks HTTP {r.status_code}: {r.text[:500]}")
            except (requests.ConnectionError, requests.Timeout) as exc:
                last = f"{type(exc).__name__}: {exc}"
            time.sleep(min(60, 2 * 2 ** attempt))
        raise RuntimeError(f"Fireworks request failed after retries: {last}")

    def invoke(self) -> LLMResponse:
        rendered = H.render_prompt(self.messages, self.tools, self.effort, self.date, prefill=self.prefill)
        d = self._request(rendered.tokens)
        choice = d["choices"][0]
        ids = choice["raw_output"]["completion_token_ids"]
        msg = H.parse_completion(ids, prefill=self.prefill)
        if self.prefill is not None:
            msg["rs_prefill_chars"] = len(self.prefill)
            self.prefill = None
        msg["rs_finish_reason"] = choice.get("finish_reason")
        self._log_usage(d, len(rendered.tokens), len(ids))
        self.messages.append(msg)
        tool_calls = [ToolCall(id=tc["id"], name=tc["function"]["name"], arguments=tc["function"]["arguments"]) for tc in msg.get("tool_calls") or []]
        return LLMResponse(reasoning=msg.get("reasoning"), response=msg.get("content"), tool_calls=tool_calls)

    def _log_usage(self, d: dict, n_prompt: int, n_completion: int) -> None:
        u = d.get("usage") or {}
        pin = u.get("prompt_tokens", n_prompt); cached = (u.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0
        out = u.get("completion_tokens", n_completion)
        cost = (pin - cached) * PRICE_IN + cached * PRICE_CACHED + out * PRICE_OUT
        self.calls += 1
        print(f"[provider-usage] t={time.time():.0f} model={self.model} in={pin} cache_read={cached} cache_write=0 out={out} "
              f"rl_in_rem=None rl_out_rem=None reasoning=0 cost={cost:.6f} served_by=Fireworks", flush=True)
        if self.usage_log is not None:
            try:
                self.usage_log.parent.mkdir(parents=True, exist_ok=True)
                with self.usage_log.open("a") as f:
                    f.write(json.dumps({"ts": datetime.now(timezone.utc).isoformat(), "call": self.calls, "prompt_tokens": pin, "cached_tokens": cached, "completion_tokens": out, "cost_usd_list": cost}) + "\n")
            except Exception:
                pass

    # -- history -------------------------------------------------------------------------------------------
    def add_tool_result(self, tool_result) -> None:
        self.messages.append({"role": "tool", "tool_call_id": tool_result.id, "content": tool_result.content})

    def add_message(self, message: dict) -> None:
        self.messages.append(message)

    def revert_last_turn(self) -> None:
        self.messages = self.messages[:-1]

    def dump_history(self) -> str:
        return json.dumps(self.messages, indent=2)

    def print_history(self) -> None:
        from agent_interp_envs.print_helpers import print_section
        for m in self.messages[-3:]:
            print_section(f"HISTORY {m['role']}", (m.get("content") or m.get("reasoning") or "")[:400])
