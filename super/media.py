"""Generic media parts for chat — images (and future audio/video) from any source.

Sources normalized into the same shape:
  - MCP ImageContent / AudioContent blocks
  - ToolResult.data["media"]
  - Embedded JSON blobs ``{"type":"image","data":"...","mimeType":"..."}``
  - Markdown ``![alt](url|data:...)``
  - Local image file paths that exist on disk

Large base64 payloads are written under ``{state_dir}/media/`` and served at
``/api/media/<id>`` so sessions stay small. Small payloads may stay as data URLs.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
from typing import Any

from .tools.base import ToolResult

KIND_IMAGE = "image"
KINDS = (KIND_IMAGE,)

# Keep tiny thumbs inline; everything else → disk.
MAX_INLINE_BYTES = 6_000
MAX_MEDIA_PER_RESULT = 12
MAX_MEDIA_PER_MESSAGE = 24
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"}
MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".bmp": "image/bmp",
    ".ico": "image/x-icon",
}
EXT_BY_MIME = {v: k for k, v in MIME_BY_EXT.items()}

# MCP / OpenAI-ish image JSON dumped into text
_IMAGE_JSON_RE = re.compile(
    r'\{\s*"type"\s*:\s*"image"\s*,\s*"data"\s*:\s*"([A-Za-z0-9+/=\s]{80,})"\s*'
    r'(?:,\s*"mimeType"\s*:\s*"([^"]+)")?\s*'
    r'(?:,\s*"mime_type"\s*:\s*"([^"]+)")?\s*'
    r'\}',
    re.DOTALL,
)
# Also tolerate mimeType before data
_IMAGE_JSON_RE2 = re.compile(
    r'\{\s*"type"\s*:\s*"image"[^{}]{0,200}?"data"\s*:\s*"([A-Za-z0-9+/=\s]{80,})"[^{}]{0,200}?\}',
    re.DOTALL,
)
_MD_IMAGE_RE = re.compile(r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)')
_PATH_RE = re.compile(
    r'(?P<p>(?:/|[A-Za-z]:\\)[^\s\'"<>]+\.(?:png|jpe?g|gif|webp|svg|bmp|ico))\b',
    re.IGNORECASE,
)
_DATA_URL_RE = re.compile(
    r'(data:image/(?:png|jpeg|jpg|gif|webp|svg\+xml);base64,[A-Za-z0-9+/=\s]+)',
    re.IGNORECASE,
)


def _media_dir(cfg: dict) -> str:
    d = os.path.join(cfg.get("state_dir") or ".super", "media")
    os.makedirs(d, exist_ok=True)
    return d


def _guess_mime(mime: str | None = None, path: str | None = None, data: bytes | None = None) -> str:
    if mime and isinstance(mime, str) and mime.startswith("image/"):
        return mime.split(";")[0].strip().lower()
    if path:
        ext = os.path.splitext(path)[1].lower()
        if ext in MIME_BY_EXT:
            return MIME_BY_EXT[ext]
    if data and len(data) >= 8:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return "image/png"
        if data[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        if data[:6] in (b"GIF87a", b"GIF89a"):
            return "image/gif"
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return "image/webp"
    return "image/png"


def _ext_for(mime: str) -> str:
    return EXT_BY_MIME.get(mime, ".bin")


def _b64_decode(raw: str) -> bytes | None:
    s = re.sub(r"\s+", "", raw or "")
    if not s:
        return None
    try:
        return base64.b64decode(s, validate=False)
    except Exception:
        try:
            return base64.b64decode(s + "=" * (-len(s) % 4))
        except Exception:
            return None


def _valid_image_bytes(raw: bytes, mime: str | None = None) -> bool:
    """Reject truncated / non-image payloads so we don't store blank garbage."""
    if not raw or len(raw) < 32:
        return False
    mime_n = (mime or "").split(";")[0].strip().lower()
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        # Require IEND trailer — truncated base64 otherwise looks like a "blank" PNG in the UI.
        return b"IEND" in raw[-32:]
    if raw[:3] == b"\xff\xd8\xff":
        return raw[-2:] == b"\xff\xd9" or b"\xff\xd9" in raw[-64:]
    if raw[:6] in (b"GIF87a", b"GIF89a"):
        return True
    if raw[:4] == b"RIFF" and len(raw) >= 12 and raw[8:12] == b"WEBP":
        return True
    if mime_n.startswith("image/") and mime_n not in (
        "image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp",
    ):
        # svg / bmp / ico — light check
        return len(raw) >= 64
    # Unknown magic — don't accept as image
    return False


def store_bytes(cfg: dict, raw: bytes, *, mime: str | None = None, hint: str = "") -> dict[str, Any]:
    """Persist bytes under state_dir/media; return a MediaPart with /api/media src."""
    mime_n = _guess_mime(mime, data=raw)
    digest = hashlib.sha256(raw).hexdigest()[:20]
    ext = _ext_for(mime_n)
    name = f"{digest}{ext}"
    path = os.path.join(_media_dir(cfg), name)
    if not os.path.isfile(path):
        with open(path, "wb") as f:
            f.write(raw)
    return {
        "kind": KIND_IMAGE,
        "id": digest,
        "src": f"/api/media/{digest}{ext}",
        "mime": mime_n,
        "bytes": len(raw),
        "alt": (hint or "")[:120],
        "source": "store",
    }


def part_from_base64(
    cfg: dict,
    b64: str,
    *,
    mime: str | None = None,
    alt: str = "",
    source: str = "base64",
) -> dict[str, Any] | None:
    raw = _b64_decode(b64)
    if not raw or len(raw) < 32:
        return None
    mime_n = _guess_mime(mime, data=raw)
    if not _valid_image_bytes(raw, mime_n):
        return None
    if len(raw) <= MAX_INLINE_BYTES:
        return {
            "kind": KIND_IMAGE,
            "src": f"data:{mime_n};base64,{base64.b64encode(raw).decode('ascii')}",
            "mime": mime_n,
            "bytes": len(raw),
            "alt": (alt or "")[:120],
            "source": source,
        }
    part = store_bytes(cfg, raw, mime=mime_n, hint=alt)
    part["source"] = source
    part["alt"] = (alt or "")[:120]
    return part


def part_from_path(cfg: dict, path: str, *, alt: str = "", source: str = "file") -> dict[str, Any] | None:
    path = (path or "").strip().strip("'\"")
    if not path:
        return None
    # Expand relative against workspace
    if not os.path.isabs(path):
        root = cfg.get("_root") or os.getcwd()
        path = os.path.abspath(os.path.join(root, path))
    else:
        path = os.path.abspath(os.path.expanduser(path))
    ext = os.path.splitext(path)[1].lower()
    if ext not in IMAGE_EXTS or not os.path.isfile(path):
        return None
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return None
    if not raw:
        return None
    mime_n = _guess_mime(path=path, data=raw)
    part = store_bytes(cfg, raw, mime=mime_n, hint=alt or os.path.basename(path))
    part["source"] = source
    part["path"] = path
    part["alt"] = (alt or os.path.basename(path))[:120]
    return part


def part_from_url(url: str, *, alt: str = "", source: str = "url") -> dict[str, Any] | None:
    url = (url or "").strip()
    if not url:
        return None
    if url.startswith("data:image/"):
        # data:image/png;base64,AAAA
        try:
            header, _, payload = url.partition(",")
            mime = header[5:].split(";")[0]  # after data:
            if ";base64" in header.lower():
                # handled via part_from_base64 by caller usually
                return {
                    "kind": KIND_IMAGE,
                    "src": url if len(url) < MAX_INLINE_BYTES * 2 else url,  # rewritten later
                    "mime": mime,
                    "alt": (alt or "")[:120],
                    "source": source,
                    "_raw_data_url": True,
                }
        except Exception:
            return None
    if url.startswith("/api/media/"):
        return {
            "kind": KIND_IMAGE,
            "src": url.split("?")[0],
            "mime": _guess_mime(path=url),
            "alt": (alt or "")[:120],
            "source": source,
        }
    if url.startswith("http://") or url.startswith("https://"):
        # Allow remote images (browser loads them). Don't fetch server-side.
        lower = url.lower()
        if any(lower.split("?", 1)[0].endswith(ext) for ext in IMAGE_EXTS) or "image" in lower:
            return {
                "kind": KIND_IMAGE,
                "src": url,
                "mime": _guess_mime(path=url.split("?", 1)[0]),
                "alt": (alt or "")[:120],
                "source": source,
            }
        # Still allow — many CDNs omit extensions
        return {
            "kind": KIND_IMAGE,
            "src": url,
            "mime": "image/*",
            "alt": (alt or "")[:120],
            "source": source,
        }
    return None


def normalize_part(cfg: dict, obj: Any, *, source: str = "unknown") -> dict[str, Any] | None:
    """Coerce assorted media dicts / blocks into a MediaPart."""
    if not isinstance(obj, dict):
        return None
    kind = str(obj.get("kind") or obj.get("type") or KIND_IMAGE).lower()
    if kind not in KINDS and kind != "image":
        # MCP uses type=image
        if kind not in ("image", "image_url"):
            return None
        kind = KIND_IMAGE

    # Already normalized with safe src
    src = obj.get("src") or obj.get("url") or ""
    if isinstance(src, str) and src.startswith(("/api/media/", "http://", "https://")):
        return {
            "kind": KIND_IMAGE,
            "id": obj.get("id"),
            "src": src.split("?")[0] if src.startswith("/api/media/") else src,
            "mime": _guess_mime(obj.get("mime") or obj.get("mimeType") or obj.get("mime_type"), path=src),
            "bytes": obj.get("bytes"),
            "alt": str(obj.get("alt") or obj.get("title") or "")[:120],
            "source": str(obj.get("source") or source)[:32],
            "path": obj.get("path"),
        }

    # data URL
    if isinstance(src, str) and src.startswith("data:image/"):
        header, _, payload = src.partition(",")
        if ";base64" in header.lower():
            mime = header[5:].split(";")[0]
            return part_from_base64(
                cfg, payload, mime=mime, alt=str(obj.get("alt") or ""), source=source
            )

    # MCP / OpenAI: data + mimeType
    data = obj.get("data") or obj.get("b64_json") or obj.get("base64")
    mime = obj.get("mime") or obj.get("mimeType") or obj.get("mime_type")
    if isinstance(data, str) and len(data) > 40:
        return part_from_base64(
            cfg, data, mime=mime if isinstance(mime, str) else None,
            alt=str(obj.get("alt") or obj.get("title") or ""), source=source,
        )

    # image_url wrapper
    image_url = obj.get("image_url")
    if isinstance(image_url, dict):
        return normalize_part(cfg, {"src": image_url.get("url"), "alt": obj.get("alt")}, source=source)
    if isinstance(image_url, str):
        return part_from_url(image_url, alt=str(obj.get("alt") or ""), source=source)

    path = obj.get("path") or obj.get("filePath") or obj.get("file_path")
    if isinstance(path, str):
        return part_from_path(cfg, path, alt=str(obj.get("alt") or ""), source=source)

    if isinstance(src, str) and src:
        # local path-like
        if src.startswith("/") or re.match(r"^[A-Za-z]:\\", src) or src.endswith(tuple(IMAGE_EXTS)):
            hit = part_from_path(cfg, src, alt=str(obj.get("alt") or ""), source=source)
            if hit:
                return hit
        return part_from_url(src, alt=str(obj.get("alt") or ""), source=source)
    return None


def _dedupe(parts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for p in parts:
        if not isinstance(p, dict):
            continue
        key = str(p.get("id") or p.get("src") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        # Drop internal flags
        clean = {k: v for k, v in p.items() if not str(k).startswith("_") and v is not None}
        if clean.get("kind") and clean.get("src"):
            out.append(clean)
        if len(out) >= MAX_MEDIA_PER_MESSAGE:
            break
    return out


def extract_from_mcp_blocks(cfg: dict, blocks: Any, *, source: str = "mcp") -> tuple[str, list[dict[str, Any]]]:
    """Split MCP content blocks into text + media parts."""
    texts: list[str] = []
    media: list[dict[str, Any]] = []
    for block in blocks or []:
        btype = str(getattr(block, "type", None) or type(block).__name__).lower()
        text = getattr(block, "text", None)
        # Prefer typed image/audio over a coincidental empty text field.
        b64 = getattr(block, "data", None)
        mime = getattr(block, "mimeType", None) or getattr(block, "mime_type", None)
        is_image = ("image" in btype) or (
            isinstance(mime, str) and mime.startswith("image/") and b64
        )
        if is_image and b64:
            part = part_from_base64(
                cfg, str(b64), mime=str(mime) if mime else None, alt="screenshot", source=source
            )
            if part:
                media.append(part)
                texts.append(f"[image:{part.get('id') or 'inline'}]")
                continue
        if text is not None and not is_image:
            # Some MCP servers embed {"type":"image","data":...} inside TextContent.
            rewritten, found = extract_from_text(cfg, str(text), source=source)
            media.extend(found)
            texts.append(rewritten)
            continue
        dumped: dict | None = None
        try:
            if hasattr(block, "model_dump"):
                dumped = block.model_dump(by_alias=True, exclude_none=True)
            elif isinstance(block, dict):
                dumped = block
        except Exception:
            dumped = None
        if dumped:
            part = normalize_part(cfg, dumped, source=source)
            if part:
                media.append(part)
                texts.append(f"[image:{part.get('id') or 'inline'}]")
                continue
            # Last resort: scan stringified block for embedded image JSON / data URLs.
            blob = json.dumps(dumped, default=str)
            rewritten, found = extract_from_text(cfg, blob, source=source)
            if found:
                media.extend(found)
                texts.append(rewritten)
            else:
                texts.append(blob[:2000])
        else:
            texts.append(str(block)[:500])
    return "\n".join(texts) if texts else "", _dedupe(media)


def extract_from_text(cfg: dict, text: str, *, source: str = "text") -> tuple[str, list[dict[str, Any]]]:
    """Pull image payloads out of free-form tool/assistant text; rewrite content."""
    if not text:
        return "", []
    media: list[dict[str, Any]] = []
    out = text

    def _sub_json(match: re.Match) -> str:
        b64 = match.group(1)
        mime = None
        if match.lastindex and match.lastindex >= 2:
            mime = match.group(2) or (match.group(3) if match.lastindex >= 3 else None)
        # Try parse full JSON for mimeType if groups missed
        try:
            obj = json.loads(match.group(0))
            mime = obj.get("mimeType") or obj.get("mime_type") or mime
            b64 = obj.get("data") or b64
        except Exception:
            pass
        part = part_from_base64(cfg, b64, mime=mime, alt="image", source=source)
        if not part:
            return match.group(0)
        media.append(part)
        return f"[image:{part.get('id') or 'inline'}]"

    out2, n = _IMAGE_JSON_RE.subn(_sub_json, out)
    if n:
        out = out2
    else:
        out = _IMAGE_JSON_RE2.sub(_sub_json, out)

    def _sub_data(match: re.Match) -> str:
        url = re.sub(r"\s+", "", match.group(1))
        header, _, payload = url.partition(",")
        mime = header[5:].split(";")[0] if header.startswith("data:") else "image/png"
        part = part_from_base64(cfg, payload, mime=mime, alt="image", source=source)
        if not part:
            return match.group(0)
        media.append(part)
        return f"[image:{part.get('id') or 'inline'}]"

    out = _DATA_URL_RE.sub(_sub_data, out)

    # Markdown images — keep markdown but also collect for album; rewrite data/file to /api/media
    def _sub_md(match: re.Match) -> str:
        alt, url = match.group(1), match.group(2)
        part = None
        if url.startswith("data:image/"):
            header, _, payload = url.partition(",")
            mime = header[5:].split(";")[0]
            part = part_from_base64(cfg, payload, mime=mime, alt=alt, source="markdown")
        elif url.startswith(("/", "~")) or re.match(r"^[A-Za-z]:\\", url) or (
            not url.startswith("http") and url.lower().endswith(tuple(IMAGE_EXTS))
        ):
            part = part_from_path(cfg, url, alt=alt, source="markdown")
        else:
            part = part_from_url(url, alt=alt, source="markdown")
        if part:
            media.append(part)
            return f"![{alt}]({part['src']})"
        return match.group(0)

    out = _MD_IMAGE_RE.sub(_sub_md, out)

    # Bare filesystem image paths
    for m in list(_PATH_RE.finditer(out)):
        p = m.group("p")
        part = part_from_path(cfg, p, alt=os.path.basename(p), source=source)
        if part:
            media.append(part)
            out = out.replace(p, f"[image:{part.get('id') or 'file'}]", 1)

    return out, _dedupe(media)


def enrich_tool_result(cfg: dict, result: ToolResult, *, tool_name: str = "") -> ToolResult:
    """Normalize any media in a tool result; strip bulky blobs from content."""
    media: list[dict[str, Any]] = []
    data = dict(result.data or {})

    for raw in data.get("media") or []:
        part = normalize_part(cfg, raw, source=str(raw.get("source") if isinstance(raw, dict) else "tool") or "tool")
        if part:
            media.append(part)

    content = result.content or ""
    content, found = extract_from_text(cfg, content, source=tool_name or "tool")
    media.extend(found)

    # Common tool data keys
    for key in ("image", "screenshot", "png", "file", "path", "filePath", "file_path"):
        val = data.get(key)
        if isinstance(val, str):
            if val.startswith("data:image/") or (len(val) > 80 and re.fullmatch(r"[A-Za-z0-9+/=\s]+", val or "")):
                part = part_from_base64(cfg, val.split(",", 1)[-1] if val.startswith("data:") else val, source="tool")
            else:
                part = part_from_path(cfg, val, source="tool") or part_from_url(val, source="tool")
            if part:
                media.append(part)

    media = _dedupe(media)[:MAX_MEDIA_PER_RESULT]
    if media:
        data["media"] = media
    elif "media" in data:
        data.pop("media", None)
    return ToolResult(ok=result.ok, content=content, data=data, taint=result.taint)


def collect_message_media(
    cfg: dict,
    *,
    content: str = "",
    tools: list | None = None,
    extra: list | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Aggregate media for an assistant turn; rewrite content markdown/data URLs."""
    media: list[dict[str, Any]] = []
    for raw in extra or []:
        part = normalize_part(cfg, raw, source="message")
        if part:
            media.append(part)
    for t in tools or []:
        if not isinstance(t, dict) or t.get("kind") != "result":
            continue
        for raw in t.get("media") or []:
            part = normalize_part(cfg, raw, source="tool")
            if part:
                media.append(part)
        # also scan truncated content leftovers
        c = t.get("content")
        if isinstance(c, str) and ("data:image" in c or '"type": "image"' in c or '"type":"image"' in c):
            _, found = extract_from_text(cfg, c, source="tool")
            media.extend(found)
    content2, found = extract_from_text(cfg, content or "", source="markdown")
    media.extend(found)
    return content2, _dedupe(media)


def resolve_media_file(cfg: dict, media_id: str) -> tuple[str, str] | None:
    """Map /api/media/<id> → (abs_path, mime)."""
    mid = (media_id or "").strip().lstrip("/")
    if not mid or ".." in mid or "/" in mid or "\\" in mid:
        return None
    # id may include extension
    base, ext = os.path.splitext(mid)
    if not re.fullmatch(r"[a-f0-9]{12,64}", base, re.I):
        return None
    directory = _media_dir(cfg)
    if ext:
        path = os.path.join(directory, mid)
        if os.path.isfile(path):
            return path, MIME_BY_EXT.get(ext.lower(), "application/octet-stream")
    # try known extensions
    for e, mime in MIME_BY_EXT.items():
        path = os.path.join(directory, base + e)
        if os.path.isfile(path):
            return path, mime
    return None


def public_part(part: dict[str, Any]) -> dict[str, Any]:
    """Slim MediaPart for SSE / session JSON."""
    out: dict[str, Any] = {
        "kind": part.get("kind") or KIND_IMAGE,
        "src": part.get("src"),
        "mime": part.get("mime") or "image/png",
    }
    for k in ("id", "alt", "bytes", "source", "path"):
        if part.get(k) is not None:
            v = part[k]
            if k == "path" and isinstance(v, str):
                out[k] = v[:240]
            elif k == "alt" and isinstance(v, str):
                out[k] = v[:120]
            elif k == "source" and isinstance(v, str):
                out[k] = v[:32]
            else:
                out[k] = v
    return out
