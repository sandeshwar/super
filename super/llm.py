"""Resilient client for Ollama-compatible chat endpoints.

Retries with exponential backoff on transient failures, validates response
shape before returning, and exposes streaming (NDJSON) plus a lightweight
health probe. All transport errors surface as LLMError; callers never parse
urllib exceptions. Stdlib only.
"""

from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.request

from .errors import LLMError


def _post(cfg: dict, path: str, payload: dict, timeout: float) -> bytes:
    url = cfg["llm"]["endpoint"].rstrip("/") + path
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except urllib.error.HTTPError as e:
        raise LLMError(f"model endpoint HTTP {e.code} on {path}") from e
    except urllib.error.URLError as e:
        raise LLMError(f"model endpoint unreachable at {url}: {e.reason}") from e
    except TimeoutError as e:
        raise LLMError(f"model endpoint timed out after {timeout}s") from e
    except OSError as e:
        raise LLMError(f"model transport failure: {e}") from e


def chat(cfg: dict, messages: list[dict], stream: bool = False) -> str:
    """Single completion with retries. Returns assistant content."""
    llm = cfg["llm"]
    timeout = float(llm.get("timeout_s", 120))
    retries = int(llm.get("retries", 2))
    payload = {"model": llm["model"], "messages": messages, "stream": False}
    last: Exception | None = None
    for attempt in range(max(1, retries + 1)):
        try:
            raw = _post(cfg, "/api/chat", payload, timeout)
            body = json.loads(raw.decode())
            content = (body.get("message") or {}).get("content", "")
            if not isinstance(content, str) or not content:
                raise LLMError("model returned an empty completion")
            return content
        except (LLMError, ValueError, KeyError) as e:
            last = e
            if attempt < retries:
                time.sleep(min(2 ** attempt + random.uniform(0, 0.4), 8))
    raise LLMError(f"completion failed after {retries + 1} attempts: {last}")


def ask(cfg: dict, prompt: str, system: str | None = None) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return chat(cfg, messages)


def chat_stream(cfg: dict, messages: list[dict]):
    """Yield content deltas from a streaming /api/chat call (NDJSON lines)."""
    llm = cfg["llm"]
    timeout = float(llm.get("timeout_s", 120))
    url = llm["endpoint"].rstrip("/") + "/api/chat"
    payload = json.dumps({"model": llm["model"], "messages": messages, "stream": True}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise LLMError(f"model stream unreachable: {e}") from e
    with resp:
        for raw in resp:
            line = raw.decode().strip() if isinstance(raw, bytes) else str(raw).strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            delta = (obj.get("message") or {}).get("content", "")
            if delta:
                yield delta
            if obj.get("done"):
                break


def list_models(cfg: dict, timeout: float = 8.0) -> list[str]:
    """List available models from /api/tags — never raises, returns [] on error."""
    try:
        url = cfg["llm"]["endpoint"].rstrip("/") + (cfg["llm"].get("health_path", "/api/tags") or "/api/tags")
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
        body = json.loads(raw.decode())
        models = body.get("models") or body.get("data") or []
        out: list[str] = []
        for m in models:
            if isinstance(m, dict):
                name = m.get("name") or m.get("model") or m.get("id")
                if name:
                    out.append(str(name))
            elif isinstance(m, str):
                out.append(m)
        return sorted(set(out))
    except Exception:
        return []


def health(cfg: dict, timeout: float = 5.0) -> tuple[bool, str]:
    """Endpoint + model presence probe. Never raises."""
    try:
        path = cfg["llm"].get("health_path", "/api/tags") or "/api/tags"
        if path == "/api/tags":
            url = cfg["llm"]["endpoint"].rstrip("/") + path
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
        else:
            raw = _post(cfg, path, {}, timeout)
        body = raw.decode()
        model = cfg["llm"]["model"].split(":")[0]
        if model.split("/")[-1].lower() in body.lower() or "models" in body.lower():
            return True, "model endpoint reachable"
        return True, "endpoint reachable (model unlisted)"
    except Exception as e:
        return False, str(e) if not isinstance(e, LLMError) else str(e)
