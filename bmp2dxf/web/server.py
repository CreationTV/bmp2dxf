"""Standard-library HTTP server that powers the local bmp2dxf web workbench.

The server is deliberately dependency free (only the Python standard library
plus the ``bmp2dxf`` package itself).  It exposes a small JSON API consumed by
``bmp2dxf/web/static/app.js`` and serves the static single page application.

Public entry points
-------------------
``create_server(host, port)``
    Build (but do not start) the :class:`~http.server.ThreadingHTTPServer`.
``run_server(host, port, open_browser, block)``
    Convenience wrapper that prints the address, optionally opens a browser
    and serves until interrupted.
"""

from __future__ import annotations

import base64
import binascii
import errno
import json
import logging
import mimetypes
import os
import re
import sys
import threading
import time
import uuid
import webbrowser
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlsplit

from .. import ConvertOptions, __version__, convert
from ..export.dxf import to_dxf_bytes
from ..export.svg import to_svg


_LOG = logging.getLogger("bmp2dxf.web")

PACKAGE_DIR = Path(__file__).resolve().parent
STATIC_DIR = PACKAGE_DIR / "static"
REPO_ROOT = PACKAGE_DIR.parent.parent
SAMPLES_DIR = REPO_ROOT / "samples"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

#: Hard cap for one request body (the frontend sends base64 encoded images).
MAX_REQUEST_BYTES = 64 * 1024 * 1024
#: Hard cap for the decoded image itself (~48 MB of binary data).
MAX_DECODED_IMAGE_BYTES = 48 * 1024 * 1024
#: Number of conversion results kept in memory for downloading.
MAX_JOBS = 32
#: Seconds after which a cached conversion result is dropped.
JOB_TTL_SECONDS = 30 * 60


STATIC_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
    ".txt": "text/plain; charset=utf-8",
    ".map": "application/json; charset=utf-8",
    ".webmanifest": "application/manifest+json",
}

SAMPLE_CONTENT_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".gif": "image/gif",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".ico": "image/x-icon",
}

DOWNLOAD_RE = re.compile(r"/api/download/([A-Za-z0-9_-]{1,64})\.(dxf|svg)")

INDEX_CSP = (
    "default-src 'self'; "
    "img-src 'self' data: blob:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'none'; "
    "form-action 'none'"
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class PortInUseError(RuntimeError):
    """Raised by :func:`create_server` when the requested port is occupied."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        super().__init__(
            f"端口 {port} 已被占用（{host}）。\n"
            "请关闭占用该端口的程序，或改用其它端口启动，例如：\n"
            f"    python -m bmp2dxf.web --port {port + 1}"
        )


class _HttpError(Exception):
    """Internal exception translated into a JSON error response."""

    def __init__(
        self, status: int, message: str, headers: dict[str, str] | None = None
    ) -> None:
        self.status = int(status)
        self.message = message
        self.headers = headers or {}
        super().__init__(message)


# ---------------------------------------------------------------------------
# Conversion job cache
# ---------------------------------------------------------------------------
@dataclass
class ConvertJob:
    """One finished conversion kept in memory so it can be downloaded."""

    job_id: str
    created_at: float
    dxf: bytes
    svg: bytes
    source_name: str
    options: dict[str, Any]


class ConversionJobCache:
    """Thread safe, size and age limited cache of conversion results."""

    def __init__(
        self, max_jobs: int = MAX_JOBS, ttl_seconds: float = JOB_TTL_SECONDS
    ) -> None:
        self._jobs: "OrderedDict[str, ConvertJob]" = OrderedDict()
        self._lock = threading.Lock()
        self._max_jobs = max(1, int(max_jobs))
        self._ttl = max(0.01, float(ttl_seconds))

    def _prune_locked(self, now: float) -> None:
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if now - job.created_at > self._ttl
        ]
        for job_id in expired:
            self._jobs.pop(job_id, None)
        while len(self._jobs) > self._max_jobs:
            self._jobs.popitem(last=False)

    def add(self, job: ConvertJob) -> None:
        with self._lock:
            now = time.time()
            self._prune_locked(now)
            while len(self._jobs) >= self._max_jobs:
                self._jobs.popitem(last=False)
            self._jobs[job.job_id] = job

    def get(self, job_id: str) -> ConvertJob | None:
        with self._lock:
            now = time.time()
            self._prune_locked(now)
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if now - job.created_at > self._ttl:
                self._jobs.pop(job_id, None)
                return None
            self._jobs.move_to_end(job_id)
            return job

    def clear(self) -> None:
        with self._lock:
            self._jobs.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._jobs)


# ---------------------------------------------------------------------------
# Path / name helpers
# ---------------------------------------------------------------------------
def _safe_resolve(base: Path, relative: str) -> Path | None:
    """Resolve ``relative`` under ``base``, rejecting traversal attempts."""
    if not relative or "\x00" in relative:
        return None
    cleaned = unquote(relative).strip().replace("\\", "/")
    parts = [part for part in cleaned.split("/") if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        return None
    if any(":" in part or "\x00" in part for part in parts):
        return None
    try:
        base_resolved = base.resolve()
        candidate = base.joinpath(*parts).resolve()
    except (OSError, ValueError, RuntimeError):
        return None
    try:
        candidate.relative_to(base_resolved)
    except ValueError:
        return None
    return candidate


def _content_type_for(path: Path, table: dict[str, str]) -> str:
    suffix = path.suffix.lower()
    if suffix in table:
        return table[suffix]
    guessed, _encoding = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def _sanitize_stem(source_name: str) -> str:
    stem = Path(str(source_name or "")).stem.strip()
    stem = re.sub(r'[\x00-\x1f\x7f/\\:*?"<>|]+', "_", stem).strip(" ._")
    return stem or "image"


def _download_file_names(
    source_name: str, extension: str, created_at: float
) -> tuple[str, str]:
    """Return ``(ascii_name, utf8_name)`` for ``Content-Disposition``."""
    stem = _sanitize_stem(source_name)
    stamp = datetime.fromtimestamp(created_at).strftime("%Y%m%d_%H%M%S")
    pretty = f"{stem}_{stamp}.{extension}"
    ascii_stem = stem.encode("ascii", "replace").decode("ascii")
    ascii_stem = re.sub(r"[^A-Za-z0-9._-]+", "_", ascii_stem).strip("._-")
    ascii_name = f"{ascii_stem or 'drawing'}_{stamp}.{extension}"
    return ascii_name, pretty


def _decode_image_base64(value: str) -> bytes:
    """Decode a base64 payload, tolerating ``data:`` URL prefixes."""
    text = str(value).strip()
    if text.startswith("data:"):
        header, separator, data = text.partition(",")
        if not separator or ";base64" not in header.lower():
            raise _HttpError(400, "图片 data URL 格式不正确，应为 base64 编码。")
        text = data
    text = "".join(text.split())
    if not text:
        raise _HttpError(400, "图片 base64 数据为空。")
    try:
        data = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        raise _HttpError(400, "图片 base64 数据无效，无法解码。") from None
    if not data:
        raise _HttpError(400, "图片 base64 解码后为空。")
    if len(data) > MAX_DECODED_IMAGE_BYTES:
        raise _HttpError(
            413, "图片文件过大（解码后上限约 48 MB），请先压缩或缩小图片。"
        )
    return data


def _list_samples() -> list[dict[str, Any]]:
    """Enumerate the images that live in the repository ``samples/`` folder."""
    if not SAMPLES_DIR.is_dir():
        return []
    samples: list[dict[str, Any]] = []
    try:
        entries = sorted(SAMPLES_DIR.iterdir(), key=lambda item: item.name.lower())
    except OSError:
        _LOG.warning("无法读取示例目录：%s", SAMPLES_DIR, exc_info=True)
        return []
    for path in entries:
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if suffix not in SAMPLE_CONTENT_TYPES:
            continue
        item: dict[str, Any] = {
            "name": path.name,
            "display_name": path.stem,
            "url": "/samples/" + quote(path.name),
            "size_bytes": path.stat().st_size,
            "format": SAMPLE_CONTENT_TYPES[suffix].split("/")[-1],
        }
        try:
            from PIL import Image

            with Image.open(path) as image:
                item["width"], item["height"] = int(image.width), int(image.height)
        except Exception:  # pragma: no cover - best effort metadata only
            pass
        samples.append(item)
    return samples


# ---------------------------------------------------------------------------
# HTTP server / request handler
# ---------------------------------------------------------------------------
class Bmp2DxfWebServer(ThreadingHTTPServer):
    """Threading HTTP server with a per-instance conversion job cache."""

    daemon_threads = True
    # On Windows ``SO_REUSEADDR`` lets a second process silently bind the same
    # port, which would hide the "port already in use" error.  Disable it there
    # (rebinding after a normal shutdown still works).  On POSIX it is safe and
    # speeds up restarting the server.
    allow_reuse_address = os.name != "nt"

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[BaseHTTPRequestHandler],
        jobs: ConversionJobCache | None = None,
    ) -> None:
        super().__init__(server_address, handler_class)
        self.jobs = jobs if jobs is not None else ConversionJobCache()
        self.started_at = time.time()

    def server_bind(self) -> None:  # pragma: no cover - trivial wrapper
        super().server_bind()


class _RequestHandler(BaseHTTPRequestHandler):
    """Routes the JSON API and the static single page application."""

    server_version = f"bmp2dxf/{__version__}"
    sys_version = ""
    protocol_version = "HTTP/1.1"
    timeout = 120

    server: Bmp2DxfWebServer

    _GET_ONLY_PATHS = frozenset({"/", "/index.html", "/api/health", "/api/samples"})

    # -- logging ---------------------------------------------------------
    def version_string(self) -> str:  # noqa: D401 - stdlib hook
        return self.server_version

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        _LOG.info("%s - %s", self.address_string(), format % args)

    # -- request entry points -------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 - stdlib naming
        self._guard(self._handle_get)

    def do_HEAD(self) -> None:  # noqa: N802 - stdlib naming
        self._guard(self._handle_get)

    def do_POST(self) -> None:  # noqa: N802 - stdlib naming
        self._guard(self._handle_post)

    def _guard(self, handler: Any) -> None:
        try:
            handler()
        except _HttpError as exc:
            if self.command == "POST":
                self.close_connection = True
            payload: dict[str, Any] = {
                "ok": False,
                "status": exc.status,
                "error": exc.message,
            }
            self._safe_json(exc.status, payload, exc.headers)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True
        except Exception:  # pragma: no cover - boundary, logged server side
            _LOG.exception("处理请求时发生未预期的错误：%s %s", self.command, self.path)
            if self.command == "POST":
                self.close_connection = True
            self._safe_json(
                500,
                {"ok": False, "status": 500, "error": "服务器内部错误，请查看控制台日志。"},
            )

    # -- response helpers ------------------------------------------------
    def _send(
        self,
        status: int,
        body: bytes,
        content_type: str,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        headers: dict[str, str] = {
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        }
        if extra_headers:
            headers.update(extra_headers)
        if self.close_connection:
            headers["Connection"] = "close"
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD" and body:
            self.wfile.write(body)

    def _send_json(
        self,
        status: int,
        payload: dict[str, Any],
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status, body, "application/json; charset=utf-8", extra_headers)

    def _safe_json(
        self,
        status: int,
        payload: dict[str, Any],
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        try:
            self._send_json(status, payload, extra_headers)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True
        except Exception:  # pragma: no cover - response already half sent
            _LOG.debug("发送错误响应失败", exc_info=True)

    # -- GET routing -----------------------------------------------------
    def _handle_get(self) -> None:
        path = urlsplit(self.path).path

        if path in ("/", "/index.html"):
            self._serve_index()
            return
        if path == "/favicon.ico":
            self._send(204, b"", "image/x-icon", {"Cache-Control": "public, max-age=86400"})
            return
        if path.startswith("/static/"):
            relative = path[len("/static/") :]
            target = _safe_resolve(STATIC_DIR, relative)
            if target is None or not target.is_file():
                raise _HttpError(404, "静态资源不存在。")
            self._send_file(
                target,
                _content_type_for(target, STATIC_CONTENT_TYPES),
                "public, max-age=3600",
            )
            return
        if path.startswith("/samples/"):
            relative = path[len("/samples/") :]
            target = _safe_resolve(SAMPLES_DIR, relative)
            if (
                target is None
                or not target.is_file()
                or target.suffix.lower() not in SAMPLE_CONTENT_TYPES
            ):
                raise _HttpError(404, "示例图片不存在。")
            self._send_file(
                target,
                _content_type_for(target, SAMPLE_CONTENT_TYPES),
                "public, max-age=60",
            )
            return
        if path == "/api/health":
            self._send_json(
                200,
                {"ok": True, "version": __version__, "service": "bmp2dxf"},
            )
            return
        if path == "/api/samples":
            self._send_json(200, {"ok": True, "samples": _list_samples()})
            return
        match = DOWNLOAD_RE.fullmatch(path)
        if match:
            self._serve_download(match.group(1), match.group(2).lower())
            return
        raise _HttpError(404, "页面或接口不存在。", {"X-Robots-Tag": "noindex"})

    def _serve_index(self) -> None:
        index_path = STATIC_DIR / "index.html"
        if not index_path.is_file():
            raise _HttpError(
                500,
                "前端文件缺失：bmp2dxf/web/static/index.html 未找到，请检查安装是否完整。",
            )
        try:
            body = index_path.read_bytes()
        except OSError:
            _LOG.exception("无法读取前端首页：%s", index_path)
            raise _HttpError(500, "无法读取前端首页文件。") from None
        headers = {
            "Cache-Control": "no-cache",
            "Content-Security-Policy": INDEX_CSP,
            "Referrer-Policy": "no-referrer",
            "X-Frame-Options": "DENY",
        }
        self._send(200, body, "text/html; charset=utf-8", headers)

    def _send_file(self, path: Path, content_type: str, cache_control: str) -> None:
        try:
            body = path.read_bytes()
        except OSError:
            _LOG.exception("无法读取文件：%s", path)
            raise _HttpError(500, "无法读取服务器文件。") from None
        self._send(200, body, content_type, {"Cache-Control": cache_control})

    def _serve_download(self, job_id: str, extension: str) -> None:
        job = self.server.jobs.get(job_id)
        if job is None:
            raise _HttpError(404, "转换结果不存在或已过期，请重新转换后再下载。")
        if extension == "dxf":
            body = job.dxf
            content_type = "image/vnd.dxf"
        else:
            body = job.svg.encode("utf-8")
            content_type = "image/svg+xml; charset=utf-8"
        ascii_name, pretty_name = _download_file_names(
            job.source_name, extension, job.created_at
        )
        disposition = (
            f'attachment; filename="{ascii_name}"; '
            f"filename*=UTF-8''{quote(pretty_name, safe='')}"
        )
        self._send(
            200,
            body,
            content_type,
            {"Content-Disposition": disposition, "Cache-Control": "no-store"},
        )

    # -- POST routing ----------------------------------------------------
    def _handle_post(self) -> None:
        path = urlsplit(self.path).path
        if path == "/api/convert":
            self._handle_convert()
            return
        if path in self._GET_ONLY_PATHS or DOWNLOAD_RE.fullmatch(path):
            raise _HttpError(
                405, "该接口只支持 GET 请求。", {"Allow": "GET, HEAD"}
            )
        raise _HttpError(404, "接口不存在。")

    def _read_body(self) -> bytes:
        raw_length = self.headers.get("Content-Length")
        if raw_length is None:
            raise _HttpError(411, "缺少 Content-Length 请求头。")
        try:
            length = int(raw_length)
        except (TypeError, ValueError):
            raise _HttpError(400, "Content-Length 请求头无效。") from None
        if length < 0:
            raise _HttpError(400, "Content-Length 请求头无效。")
        if length > MAX_REQUEST_BYTES:
            raise _HttpError(
                413, "请求体过大（上限约 64 MB），请先压缩或缩小图片。"
            )
        if length == 0:
            raise _HttpError(400, "请求体为空。")
        body = self.rfile.read(length)
        if body is None or len(body) < length:
            raise _HttpError(400, "请求体读取不完整。")
        return body

    def _handle_convert(self) -> None:
        raw_body = self._read_body()
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise _HttpError(400, "请求体不是有效的 JSON。") from None
        if not isinstance(payload, dict):
            raise _HttpError(400, "请求体必须是 JSON 对象。")

        image_value = payload.get("image_base64") or payload.get("imageBase64")
        if not isinstance(image_value, str) or not image_value.strip():
            raise _HttpError(400, "缺少 image_base64 字段（图片的 base64 数据）。")
        filename = str(payload.get("filename") or "image")
        options_payload = payload.get("options") or {}
        if not isinstance(options_payload, dict):
            raise _HttpError(400, "options 字段必须是 JSON 对象。")

        try:
            options = ConvertOptions.from_dict(options_payload)
        except (ValueError, TypeError) as exc:
            raise _HttpError(400, f"参数错误：{exc}") from None

        image_bytes = _decode_image_base64(image_value)

        try:
            result = convert(image_bytes, options)
        except ValueError as exc:
            raise _HttpError(400, f"转换失败：{exc}") from None
        except MemoryError:
            raise _HttpError(400, "图片过大，转换时内存不足，请先缩小图片。") from None
        except Exception:  # pragma: no cover - boundary, logged server side
            _LOG.exception("图片转换失败：%s", filename)
            raise _HttpError(
                500, "转换过程中出现内部错误，请查看控制台日志。"
            ) from None

        try:
            dxf_bytes = to_dxf_bytes(result)
            svg_text = to_svg(result)
        except Exception:  # pragma: no cover - boundary, logged server side
            _LOG.exception("导出 DXF/SVG 失败：%s", filename)
            raise _HttpError(500, "导出结果失败，请查看控制台日志。") from None

        job_id = uuid.uuid4().hex
        created_at = time.time()
        job = ConvertJob(
            job_id=job_id,
            created_at=created_at,
            dxf=dxf_bytes,
            svg=svg_text,
            source_name=filename,
            options=options.to_dict(),
        )
        self.server.jobs.add(job)

        stats = result.stats.to_dict()
        response = {
            "ok": True,
            "job_id": job_id,
            "svg": svg_text,
            "stats": stats,
            "warnings": list(result.warnings),
            "mode_used": str(stats.get("mode_used") or options.mode),
            "auto_reason": str(stats.get("auto_reason") or ""),
            "source_width": int(result.source_width or stats.get("source_width") or 0),
            "source_height": int(
                result.source_height or stats.get("source_height") or 0
            ),
            "image_format": result.image_format,
            "filename": filename,
            "elapsed_ms": stats.get("duration_ms", 0.0),
            "downloads": {
                "dxf": f"/api/download/{job_id}.dxf",
                "svg": f"/api/download/{job_id}.svg",
            },
        }
        self._send_json(200, response)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def _is_address_in_use(exc: OSError) -> bool:
    winerror = getattr(exc, "winerror", None)
    if winerror in (10048, 10013):  # WSAEADDRINUSE / WSAEACCES
        return True
    return exc.errno in (errno.EADDRINUSE, errno.EACCES)


def create_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> Bmp2DxfWebServer:
    """Create (but do not start) the local web server.

    Parameters
    ----------
    host:
        Interface to bind.  Defaults to ``127.0.0.1`` (local only).
    port:
        TCP port.  Use ``0`` to let the operating system choose a free port
        (the real port is then available as ``server.server_address[1]``).

    Raises
    ------
    PortInUseError
        If the requested port cannot be bound.
    """
    try:
        port_number = int(port)
    except (TypeError, ValueError):
        raise ValueError(f"port 必须是整数，收到 {port!r}") from None
    try:
        server = Bmp2DxfWebServer((str(host), port_number), _RequestHandler)
    except OSError as exc:
        if _is_address_in_use(exc):
            raise PortInUseError(str(host), port_number) from exc
        raise
    _LOG.info(
        "Web 服务已创建：http://%s:%s/",
        server.server_address[0],
        server.server_address[1],
    )
    return server


def _configure_logging() -> None:
    if _LOG.handlers:
        return
    handler = logging.StreamHandler(stream=sys.stderr)
    handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(message)s", datefmt="%H:%M:%S")
    )
    _LOG.addHandler(handler)
    _LOG.setLevel(logging.INFO)
    _LOG.propagate = False


def run_server(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    open_browser: bool = True,
    block: bool = True,
) -> Any:
    """Start the local web UI.

    Parameters
    ----------
    host, port:
        Passed to :func:`create_server`.
    open_browser:
        Open the workbench in the default browser after the server starts.
    block:
        ``True`` (default) serves in the current thread until interrupted.
        ``False`` starts the server on a background thread and returns the
        server object; the caller then owns ``shutdown()`` / ``server_close()``.

    Returns
    -------
    int or Bmp2DxfWebServer
        ``0`` after a clean blocking shutdown, ``1`` if the port is occupied,
        or the server instance when ``block=False``.
    """
    _configure_logging()
    try:
        server = create_server(host, port)
    except PortInUseError as exc:
        print(f"[bmp2dxf] 启动失败：{exc}", file=sys.stderr, flush=True)
        return 1

    socket_host, socket_port = server.server_address[0], server.server_address[1]
    url = f"http://{socket_host}:{socket_port}/"
    print("", flush=True)
    print("  bmp2dxf Web 工作台", flush=True)
    print(f"  版本: {__version__}   地址: {url}", flush=True)
    print("  在本窗口中按 Ctrl+C 可停止服务。", flush=True)
    print("", flush=True)

    if open_browser:
        timer = threading.Timer(0.5, webbrowser.open, args=(url,))
        timer.daemon = True
        timer.start()

    if not block:
        thread = threading.Thread(
            target=server.serve_forever, name="bmp2dxf-web", daemon=True
        )
        thread.start()
        server.serve_thread = thread  # type: ignore[attr-defined]
        return server

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[bmp2dxf] 已停止 Web 服务。", flush=True)
    finally:
        server.server_close()
    return 0


__all__ = [
    "Bmp2DxfWebServer",
    "ConversionJobCache",
    "ConvertJob",
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "PortInUseError",
    "create_server",
    "run_server",
]
