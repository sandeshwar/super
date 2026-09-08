"""Resilient client for Ollama-compatible chat endpoints.

Retries with exponential backoff on transient failures, validates response
shape before returning, and exposes streaming (NDJSON) plus a lightweight
health probe. All transport errors surface as LLMError; callers never parse
urllib exceptions. Stdlib only.
"""

from __future__ import annotations

import json
import random
import re
import time
import urllib.error
import urllib.request

from .errors import LLMError

_THINK_TAG_RE = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)


# Graded effort for Ollama / mlx-serve thinking models.
THINK_LEVELS_GRADED: tuple[str, ...] = ("off", "low", "medium", "high", "max")
_THINK_CAP_ALIASES = frozenset({"thinking", "reasoning"})
_THINK_NAME_HINTS = (
    "thinking",
    "reason",
    "r1",
    "qwq",
    "deepseek-r",
    "qwen3",
    "qwen4",
    "gpt-oss",
)


def think_param(cfg: dict) -> bool | str:
    """Normalize llm.think for the Ollama chat payload (top-level ``think``)."""
    raw = (cfg.get("llm") or {}).get("think", True)
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        s = raw.strip().lower()
        if s in ("false", "0", "no", "off", ""):
            return False
        if s in ("true", "1", "yes", "on"):
            return True
        if s in ("low", "medium", "high", "max"):
            return s
    return bool(raw)


def think_level(cfg: dict) -> str:
    """UI-facing think level: off|low|medium|high|max."""
    raw = think_param(cfg)
    if raw is False:
        return "off"
    if raw is True:
        return "medium"
    if isinstance(raw, str) and raw in THINK_LEVELS_GRADED[1:]:
        return raw
    return "medium"


def parse_think_level(value) -> bool | str:
    """Coerce a UI / API value into a stored llm.think setting."""
    if isinstance(value, bool):
        return value
    s = str(value or "").strip().lower()
    if s in ("false", "0", "no", "off", ""):
        return False
    if s in ("true", "1", "yes", "on"):
        return True
    if s in ("low", "medium", "high", "max"):
        return s
    raise ValueError("think must be off|low|medium|high|max")


def _with_think(payload: dict, cfg: dict) -> dict:
    payload["think"] = think_param(cfg)
    return payload


def _name_suggests_thinking(name: str) -> bool:
    n = (name or "").lower()
    return any(h in n for h in _THINK_NAME_HINTS)


def model_capabilities(cfg: dict, model: str | None = None, timeout: float = 8.0) -> list[str]:
    """Best-effort capability list from /v1/models and/or /api/show."""
    llm = cfg.get("llm") or {}
    target = (model or llm.get("model") or "").strip()
    if not target:
        return []
    base = str(llm.get("endpoint") or "").rstrip("/")
    if not base:
        return []
    aliases = _model_aliases(target)
    found: set[str] = set()

    def _absorb(caps) -> None:
        if not isinstance(caps, (list, tuple)):
            return
        for c in caps:
            if isinstance(c, str) and c.strip():
                found.add(c.strip().lower())

    # 1) /v1/models (mlx-serve: reasoning, tool_use, …)
    try:
        req = urllib.request.Request(base + "/v1/models", method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
        rows = body.get("data") or body.get("models") or []
        for row in rows:
            if not isinstance(row, dict):
                continue
            rid = str(row.get("id") or row.get("name") or row.get("model") or "")
            if aliases & _model_aliases(rid) or any(a in rid or rid in a for a in aliases):
                _absorb(row.get("capabilities"))
                meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
                _absorb(meta.get("capabilities"))
                break
    except Exception:
        pass

    # 2) Ollama /api/show (thinking, tools, …)
    try:
        raw = _post(cfg, "/api/show", {"name": target}, timeout)
        body = json.loads(raw.decode())
        if isinstance(body, dict):
            _absorb(body.get("capabilities"))
    except Exception:
        pass

    return sorted(found)


def think_levels_for(
    cfg: dict,
    model: str | None = None,
    timeout: float = 8.0,
    caps: list[str] | None = None,
) -> list[str]:
    """Levels the UI should offer for the active model/provider."""
    cap_set = set(caps if caps is not None else model_capabilities(cfg, model=model, timeout=timeout))
    if cap_set & _THINK_CAP_ALIASES:
        return list(THINK_LEVELS_GRADED)
    name = (model or (cfg.get("llm") or {}).get("model") or "")
    if _name_suggests_thinking(name):
        return list(THINK_LEVELS_GRADED)
    # Unknown / non-thinking: only off (selector hidden when len<=1)
    return ["off"]


def think_info(cfg: dict, model: str | None = None, timeout: float = 8.0) -> dict:
    """Bundle for /api/models and settings: current level + available choices."""
    caps = model_capabilities(cfg, model=model, timeout=timeout)
    levels = think_levels_for(cfg, model=model, timeout=timeout, caps=caps)
    current = think_level(cfg)
    if current not in levels:
        current = levels[-1] if len(levels) > 1 else "off"
    return {
        "think": current,
        "think_levels": levels,
        "think_supported": len(levels) > 1,
        "capabilities": caps,
    }


def split_think_tags(content: str) -> tuple[str, str]:
    """Fallback: peel ``<think>`` blocks out of content when the API didn't."""
    if not content or "<think>" not in content.lower():
        return content or "", ""
    parts = _THINK_TAG_RE.findall(content)
    if not parts:
        return content, ""
    thinking = "\n\n".join(p.strip() for p in parts if p.strip())
    cleaned = _THINK_TAG_RE.sub("", content).strip()
    return cleaned, thinking


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

    Prefill tok/s uses *uncached* prompt tokens when the provider reports a cache
    count. mlx-serve often omits that field on KV hits, leaving a tiny
    ``prompt_eval_duration`` against the full ``prompt_eval_count`` (looks like
    10k+ tok/s). In that case we suppress ``prefill_tps`` and flag the hit.
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

    # Tokens actually run through prefill this turn (exclude KV hits when known).
    prefill_n: int | float | None = prompt_n
    if (
        isinstance(prompt_n, (int, float))
        and isinstance(cached, (int, float))
        and cached >= 0
    ):
        prefill_n = max(0, int(prompt_n) - int(cached))

    prefill = _tps(prefill_n, prompt_ns) if prefill_n else None
    # No cache count from provider: duration collapsed on a warm prompt looks like
    # absurd throughput. >4k tok/s for a multi-hundred-token prompt ≈ cache hit.
    if (
        prefill is not None
        and isinstance(prompt_n, (int, float))
        and prompt_n >= 64
        and prefill >= 4000
        and not (isinstance(cached, (int, float)) and cached > 0)
    ):
        out["prefill_cached"] = True
        prefill = None
    elif (
        isinstance(cached, (int, float))
        and isinstance(prompt_n, (int, float))
        and cached > 0
        and cached >= 0.85 * prompt_n
    ):
        out["prefill_cached"] = True

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
    payload: dict = _with_think(
        {"model": llm["model"], "messages": messages, "stream": False}, cfg
    )
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
            thinking = msg.get("thinking") or ""
            if content and not thinking:
                content, tagged = split_think_tags(content)
                if tagged:
                    msg = {**msg, "content": content, "thinking": tagged}
                    thinking = tagged
            if not content and not tool_calls and not thinking:
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
      {"thinking_delta": str} — reasoning token/chunk (when llm.think enabled)
      {"delta": str}          — content token/chunk
      {"tool_calls": list}    — full tool_calls when present (usually on final frame)
      {"usage": dict}         — provider timing when done
      {"message": dict}       — assembled assistant message at end (content + tool_calls + thinking)
    """
    llm = cfg["llm"]
    timeout = float(llm.get("timeout_s", 120))
    url = llm["endpoint"].rstrip("/") + "/api/chat"
    payload_obj: dict = _with_think(
        {"model": llm["model"], "messages": messages, "stream": True}, cfg
    )
    if tools:
        payload_obj["tools"] = tools
    payload = json.dumps(payload_obj).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=timeout)
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise LLMError(f"model stream unreachable: {e}") from e

    content_parts: list[str] = []
    thinking_parts: list[str] = []
    tool_calls: list = []

    def _assemble() -> dict:
        content = "".join(content_parts)
        thinking = "".join(thinking_parts)
        if content and not thinking:
            content, tagged = split_think_tags(content)
            if tagged:
                thinking = tagged
        assembled: dict = {
            "role": "assistant",
            "content": content,
        }
        if thinking:
            assembled["thinking"] = thinking
        if tool_calls:
            assembled["tool_calls"] = tool_calls
        return assembled

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
            think_delta = msg.get("thinking") or ""
            if think_delta:
                thinking_parts.append(think_delta)
                yield {"thinking_delta": think_delta}
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
                yield {"message": _assemble()}
                return
        # EOF without a done frame — still finish so the agent loop doesn't hang.
        if content_parts or tool_calls or thinking_parts:
            if tool_calls:
                yield {"tool_calls": tool_calls}
            yield {"message": _assemble()}


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
