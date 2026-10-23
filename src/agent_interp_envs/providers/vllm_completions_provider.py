"""Raw-completions provider for Qwen3.5-family models served by our own vLLM (assistantaxis.md guardrail 1).

The prompt is rendered client-side with the model's published chat template (`qwen_template`), sent to vLLM's
/v1/completions, and the completion is parsed back into reasoning, content and tool calls. vLLM is asked to return the
exact token ids it used (`return_token_ids`); each assistant message stores them under `_vllm`:

    {"prompt_len": int, "prompt_sha256": str, "completion_token_ids": [...], "finish_reason": str}

so an activation replay can rebuild every call's exact token sequence (render the prefix, tokenize, check the hash)
and append the stored completion ids, without trusting a re-render of generated text.

Endpoint: VLLM_BASE_URL (e.g. the Modal web URL ending in /v1) and VLLM_API_KEY, from the environment (.env).
Sampling: temperature / top_p from the config, else Qwen's recommended thinking-mode defaults (0.6 / 0.95, top_k 20).
"""
from __future__ import annotations

import hashlib
import os

from dotenv import load_dotenv
from openai import APIConnectionError, APITimeoutError, InternalServerError, OpenAI, RateLimitError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from agent_interp_envs.providers import olmo3_template, qwen_template
from agent_interp_envs.providers.base import BaseProvider
from agent_interp_envs.types import LLMResponse, ToolCall

load_dotenv()

DEFAULT_MAX_TOKENS = 32768
CONTEXT = 262144
QWEN_DEFAULTS = {"temperature": 0.6, "top_p": 0.95, "top_k": 20}
# per model family: template module, sampling defaults, context, stop strings, completion cap
FAMILIES = {
    "qwen": {"tmpl": qwen_template, "sampling": QWEN_DEFAULTS, "context": CONTEXT, "stop": None, "max_tokens": DEFAULT_MAX_TOKENS},
    "olmo": {"tmpl": olmo3_template, "sampling": olmo3_template.SAMPLING, "context": 65536, "stop": olmo3_template.STOP, "max_tokens": 8192},
}


def family(model: str) -> dict:
    return FAMILIES["olmo"] if "olmo" in model.lower() else FAMILIES["qwen"]


class VLLMCompletionsProvider(BaseProvider):
    def __init__(self, model: str, messages: list[dict], tools: list[dict], temperature: float | None = None,
                 top_p: float | None = None, reasoning_effort: str | None = None) -> None:
        base_url = os.environ.get("VLLM_BASE_URL")
        if not base_url:
            raise ValueError("vllm_completions needs VLLM_BASE_URL (the vLLM server's /v1 URL) in the environment")
        self.client = OpenAI(base_url=base_url, api_key=os.environ.get("VLLM_API_KEY") or "EMPTY", timeout=1800)
        self.model = model
        self.messages = messages
        self.tools = tools
        self.fam = family(model)
        self.temperature = self.fam["sampling"]["temperature"] if temperature is None else temperature
        self.top_p = self.fam["sampling"]["top_p"] if top_p is None else top_p

    def render(self) -> str:
        return self.fam["tmpl"].render_prompt(self.messages, self.tools)

    @retry(stop=stop_after_attempt(10), wait=wait_exponential(multiplier=2, min=2, max=120),
           retry=retry_if_exception_type((RateLimitError, APITimeoutError, APIConnectionError, InternalServerError)))
    def _complete(self, prompt: str):
        f = self.fam
        r = self.client.completions.create(
            model=self.model, prompt=prompt, max_tokens=max(16, min(f["max_tokens"], f["context"] - len(prompt) // 3 - 256)),
            temperature=self.temperature, top_p=self.top_p, stop=f["stop"],
            extra_body={"top_k": f["sampling"]["top_k"], "return_token_ids": True, "skip_special_tokens": False})
        c = r.choices[0]
        prompt_ids = getattr(c, "prompt_token_ids", None) or (getattr(r, "model_extra", None) or {}).get("prompt_token_ids") or []
        return c.text, list(prompt_ids), list(getattr(c, "token_ids", None) or []), c.finish_reason

    def invoke(self) -> LLMResponse:
        prompt = self.render()
        text, prompt_ids, completion_ids, finish = self._complete(prompt)
        parsed = self.fam["tmpl"].parse_completion(text, self.tools)
        message = parsed["message"]
        message["_vllm"] = {"prompt_len": len(prompt_ids), "prompt_sha256": hashlib.sha256(str(prompt_ids).encode()).hexdigest() if prompt_ids else None,
                            "prompt_text_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "completion_token_ids": completion_ids,
                            "finish_reason": finish}
        self.messages.append(message)
        calls = [ToolCall(id=tc["id"], name=tc["function"]["name"], arguments=tc["function"]["arguments"]) for tc in message.get("tool_calls") or []]
        return LLMResponse(reasoning=message.get("reasoning_content"), response=message.get("content"), tool_calls=calls or None)

    def add_tool_result(self, tool_result) -> None:
        self.messages.append({"role": "tool", "tool_call_id": tool_result.id, "content": tool_result.content})

    def add_message(self, message: dict) -> None:
        self.messages.append(message)

    def revert_last_turn(self) -> None:
        if self.messages:
            self.messages.pop()

    def print_history(self) -> None:
        from agent_interp_envs.providers.fireworks_provider import FireworksProvider
        FireworksProvider.print_history(self)
