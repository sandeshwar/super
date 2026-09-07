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


def extract_usage(body: dict | None) -> dict | None:
    """Normalize Ollama/mlx-serve timing fields into UI-friendly stats.

    Durations from the provider are nanoseconds. Returns None if no timing present.
    """
    if not isinstance(body, dict):
        return None
    prompt_n = body.get("prompt_eval_count")
    eval_n = body.get("eval_count")
    prompt_ns = body.get("prompt_eval_duration")
    eval_ns = body.get("eval_duration")
    total_ns = body.get("total_duration")
    load_ns = body.get("load_duration")
    cached = body.get("prompt_eval_cached_count")
    if not any(isinstance(x, (int, float)) and x for x in (prompt_n, eval_n, prompt_ns, eval_ns, total_ns)):
        return None

    def _tps(count, ns) -> float | None:
        if not isinstance(count, (int, float)) or not isinstance(ns, (int, float)):
            return None
        if count <= 0 or ns <= 0:
            return None
        return round(float(count) / (float(ns) / 1e9), 2)

    def _ms(ns) -> float | None:
        if not isinstance(ns, (int, float)) or ns < 0:
            return None
        return round(float(ns) / 1e6, 1)

    out: dict = {"source": "provider"}
    if isinstance(prompt_n, (int, float)):
        out["prompt_tokens"] = int(prompt_n)
    if isinstance(eval_n, (int, float)):
        out["completion_tokens"] = int(eval_n)
    if isinstance(cached, (int, float)) and cached >= 0:
        out["cached_tokens"] = int(cached)
    prefill = _tps(prompt_n, prompt_ns)
    decode = _tps(eval_n, eval_ns)
    if prefill is not None:
        out["prefill_tps"] = prefill
    if decode is not None:
        out["decode_tps"] = decode
    for key, ns in (
        ("prompt_ms", prompt_ns),
        ("eval_ms", eval_ns),
        ("load_ms", load_ns),
        ("total_ms", total_ns),
    ):
        ms = _ms(ns)
        if ms is not None:
            out[key] = ms
    if body.get("done_reason"):
        out["done_reason"] = str(body.get("done_reason"))
    return out


def chat_message(cfg: dict, messages: list[dict], tools: list[dict] | None = None) -> tuple[dict, dict | None]:
    """Single completion returning (assistant message, usage stats|None)."""
    llm = cfg["llm"]
    timeout = float(llm.get("timeout_s", 120))
    retries = int(llm.get("retries", 2))
    payload: dict = {"model": llm["model"], "messages": messages, "stream": False}
    if tools:
        payload["tools"] = tools
    last: Exception | None = None
    for attempt in range(max(1, retries + 1)):
        try:
            raw = _post(cfg, "/api/chat", payload, timeout)
            body = json.loads(raw.decode())
            msg = body.get("message") or {}
            if not isinstance(msg, dict):
                raise LLMError("model returned a malformed message")
            content = msg.get("content") or ""
            tool_calls = msg.get("tool_calls") or []
            if not content and not tool_calls:
                raise LLMError("model returned an empty completion")
            return msg, extract_usage(body if isinstance(body, dict) else None)
        except (LLMError, ValueError, KeyError) as e:
            last = e
            if attempt < retries:
                time.sleep(min(2 ** attempt + random.uniform(0, 0.4), 8))
    raise LLMError(f"completion failed after {retries + 1} attempts: {last}")


def chat(cfg: dict, messages: list[dict], stream: bool = False) -> str:
    """Single completion with retries. Returns assistant content."""
    msg, _usage = chat_message(cfg, messages, tools=None)
    content = msg.get("content") or ""
    if not isinstance(content, str) or not content:
        raise LLMError("model returned an empty completion")
    return content


def ask(cfg: dict, prompt: str, system: str | None = None) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    return chat(cfg, messages)


def chat_stream(cfg: dict, messages: list[dict], tools: list[dict] | None = None):
    """Yield stream events from /api/chat.

    Yields:
      {"delta": str}          — content token/chunk
      {"tool_calls": list}    — full tool_calls when present (usually on final frame)
      {"usage": dict}         — provider timing when done
      {"message": dict}       — assembled assistant message at end (content + tool_calls)
    """
    llm = cfg["llm"]
    timeout = float(llm.get("timeout_s", 120))
    url = llm["endpoint"].rstrip("/") + "/api/chat"
    payload_obj: dict = {"model": llm["model"], "messages": messages, "stream": True}
    if tools:
        payload_obj["tools"] = tools
    payload = json.dumps(payload_obj).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise LLMError(f"model stream unreachable: {e}") from e

    content_parts: list[str] = []
    tool_calls: list = []
    with resp:
        for raw in resp:
            line = raw.decode().strip() if isinstance(raw, bytes) else str(raw).strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if not isinstance(obj, dict):
                continue
            msg = obj.get("message") or {}
            if not isinstance(msg, dict):
                msg = {}
            delta = msg.get("content") or ""
            if delta:
                content_parts.append(delta)
                yield {"delta": delta}
            tcs = msg.get("tool_calls")
            if isinstance(tcs, list) and tcs:
                tool_calls = tcs
            if obj.get("done"):
                if tool_calls:
                    yield {"tool_calls": tool_calls}
                usage = extract_usage(obj)
                if usage:
                    yield {"usage": usage}
                assembled = {
                    "role": "assistant",
                    "content": "".join(content_parts),
                }
                if tool_calls:
                    assembled["tool_calls"] = tool_calls
                yield {"message": assembled}
                break


def chat_stream_text(cfg: dict, messages: list[dict]):
    """Back-compat: yield only {delta}/{usage} (no tools)."""
    for ev in chat_stream(cfg, messages, tools=None):
        if "delta" in ev or "usage" in ev:
            yield ev


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


def _parse_context_length(obj: dict) -> int | None:
    """Extract a positive context window from provider model metadata."""
    if not isinstance(obj, dict):
        return None
    for key in ("context_length", "max_model_len", "model_max_tokens", "max_tokens", "n_ctx", "num_ctx"):
        v = obj.get(key)
        if isinstance(v, (int, float)) and int(v) > 0:
            return int(v)
        if isinstance(v, str) and v.strip().isdigit():
            n = int(v.strip())
            if n > 0:
                return n
    meta = obj.get("meta")
    if isinstance(meta, dict):
        hit = _parse_context_length(meta)
        if hit:
            return hit
    info = obj.get("model_info") or obj.get("info")
    if isinstance(info, dict):
        for k, v in info.items():
            if "context_length" in str(k).lower() or str(k).lower().endswith(".context_length"):
                if isinstance(v, (int, float)) and int(v) > 0:
                    return int(v)
        hit = _parse_context_length(info)
        if hit:
            return hit
    params = obj.get("parameters")
    if isinstance(params, str) and params.strip():
        # Ollama Modelfile params: "num_ctx 8192\n..."
        for line in params.splitlines():
            parts = line.strip().split()
            if len(parts) >= 2 and parts[0].lower() in ("num_ctx", "n_ctx", "context_length"):
                try:
                    n = int(parts[1])
                    if n > 0:
                        return n
                except ValueError:
                    pass
    return None


def _model_aliases(name: str) -> set[str]:
    n = (name or "").strip()
    if not n:
        return set()
    out = {n, n.split(":")[0]}
    # strip registry path variants
    out.add(n.split("/")[-1])
    out.add(n.split("/")[-1].split(":")[0])
    return {x for x in out if x}


def model_context_length(cfg: dict, model: str | None = None, timeout: float = 8.0) -> int | None:
    """Fetch context window for the active (or given) model from the LLM provider.

    Prefers OpenAI-compatible ``/v1/models`` (mlx-serve), then Ollama ``/api/show``.
    Returns None when the provider does not expose a length — callers must not invent one.
    """
    llm = cfg.get("llm") or {}
    target = (model or llm.get("model") or "").strip()
    if not target:
        return None
    base = str(llm.get("endpoint") or "").rstrip("/")
    if not base:
        return None
    aliases = _model_aliases(target)

    # 1) /v1/models — mlx-serve puts context_length on each model object
    try:
        req = urllib.request.Request(base + "/v1/models", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
        rows = body.get("data") or body.get("models") or []
        best = None
        for row in rows:
            if not isinstance(row, dict):
                continue
            rid = str(row.get("id") or row.get("name") or row.get("model") or "")
            if not rid:
                continue
            if aliases & _model_aliases(rid) or any(a in rid or rid in a for a in aliases):
                hit = _parse_context_length(row)
                if hit:
                    return hit
            if best is None:
                best = _parse_context_length(row)
        # if only one model listed, use it
        if len(rows) == 1 and best:
            return best
    except Exception:
        pass

    # 2) Ollama /api/show
    try:
        raw = _post(cfg, "/api/show", {"name": target}, timeout)
        body = json.loads(raw.decode())
        hit = _parse_context_length(body if isinstance(body, dict) else {})
        if hit:
            return hit
    except Exception:
        pass

    # 3) /api/tags details (rare)
    try:
        url = base + (llm.get("health_path") or "/api/tags")
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
        for row in body.get("models") or []:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or row.get("model") or "")
            if aliases & _model_aliases(name):
                hit = _parse_context_length(row) or _parse_context_length(row.get("details") or {})
                if hit:
                    return hit
    except Exception:
        pass
    return None


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
