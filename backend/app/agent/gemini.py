"""Gemini calls with model fallback (ported from Grinta): if one model fails
(e.g. 503 overloaded), times out, or returns an empty answer, the next one is
tried."""
import time

from google import genai
from google.genai import types

from ..config import get_settings

_client: genai.Client | None = None


class AgentUnavailable(RuntimeError):
    """The agent can't run (no API key, or every model failed)."""


def client() -> genai.Client:
    global _client
    if _client is None:
        key = get_settings().gemini_api_key
        if not key:
            raise AgentUnavailable("GEMINI_API_KEY is not set")
        _client = genai.Client(
            api_key=key,
            http_options=types.HttpOptions(
                timeout=int(get_settings().gemini_timeout_seconds * 1000),   # milliseconds
                # No retries inside the SDK: a slow or failing model should hand
                # over to the next model right away.
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
    return _client


def models() -> list[str]:
    return [m.strip() for m in get_settings().gemini_models.split(",") if m.strip()]


def generate(history: list[types.Content], system_instruction: str,
             tools: list[types.Tool] | None,
             deadline: float | None = None) -> types.GenerateContentResponse:
    """deadline: a time.monotonic() value; no new model is tried after it."""
    last_error: Exception | None = None
    for name in models():
        if deadline is not None and time.monotonic() > deadline:
            last_error = last_error or TimeoutError("reply deadline passed")
            break
        started = time.monotonic()
        try:
            resp = client().models.generate_content(
                model=name,
                contents=history,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    tools=tools or None,
                ),
            )
            # A "successful" response can be empty (safety block, max tokens…):
            # treat it as a failure and try the next model.
            cand = (resp.candidates or [None])[0]
            if cand is None or cand.content is None or not cand.content.parts:
                reason = getattr(cand, "finish_reason", None) if cand else None
                print(f"[gemini] {name} returned no content (finish_reason={reason}) — trying next")
                last_error = RuntimeError(f"empty response from {name} (finish_reason={reason})")
                continue
            return resp
        except AgentUnavailable:
            raise
        except Exception as e:  # noqa: BLE001 — any model error falls through to the next
            print(f"[gemini] {name} failed after {time.monotonic() - started:.1f}s: "
                  f"{str(e)[:300]} — trying next")
            last_error = e
    raise AgentUnavailable(f"all models failed: {last_error}")
