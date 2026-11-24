"""Tests for the bmp2dxf local web workbench (:mod:`bmp2dxf.web`).

The tests start a real server on an ephemeral port (``port=0``) in a daemon
thread and talk to it with :mod:`urllib.request`, covering the JSON API,
downloads, static assets and security edge cases.
"""

from __future__ import annotations

import base64
import io
import json
import threading
import time
import urllib.error
import urllib.request

import ezdxf
import pytest
from PIL import Image, ImageDraw

from bmp2dxf.web import PortInUseError, create_server
from bmp2dxf.web.server import ConversionJobCache, ConvertJob

from tools import color_art_image, to_png


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_line_art_png(width: int = 400, height: int = 300) -> bytes:
    """Create a small synthetic line drawing: rectangle, polyline and circle."""
    image = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(image)
    draw.rectangle([40, 40, width - 40, height - 40], outline=0, width=4)
    draw.line(
        [60, height // 2, width // 2, 70, width - 60, height // 2],
        fill=0,
        width=4,
    )
    draw.ellipse(
        [width // 2 - 50, height - 110, width // 2 + 50, height - 30],
        outline=0,
        width=4,
    )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


LINE_ART_PNG = _make_line_art_png()


def _http(
    method: str,
    url: str,
    body: bytes | dict | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 90.0,
) -> tuple[int, dict[str, str], bytes]:
    data = None
    request_headers = dict(headers or {})
    if body is not None:
        if isinstance(body, (bytes, bytearray)):
            data = bytes(body)
        else:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json; charset=utf-8")
    request = urllib.request.Request(
        url, data=data, headers=request_headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as exc:  # pragma: no cover - exercised a lot
        return exc.code, dict(exc.headers), exc.read()


def _json(body: bytes) -> dict:
    return json.loads(body.decode("utf-8"))


def _header(headers: dict[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if key.lower() == name.lower():
            return value
    return None


def _convert_payload(**overrides) -> dict:
    payload = {
        "image_base64": base64.b64encode(LINE_ART_PNG).decode("ascii"),
        "filename": "test_line_art.png",
        "options": {"mode": "auto", "precision": 70},
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def web_server():
    server = create_server(port=0)
    port = int(server.server_address[1])
    thread = threading.Thread(
        target=server.serve_forever, name="test-bmp2dxf-web", daemon=True
    )
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.fixture(scope="module")
def conversion(web_server: str) -> dict:
    status, headers, body = _http(
        "POST", web_server + "/api/convert", _convert_payload()
    )
    assert status == 200, body.decode("utf-8", "replace")
    assert "application/json" in (_header(headers, "Content-Type") or "")
    data = _json(body)
    assert data["ok"] is True
    return data


# ---------------------------------------------------------------------------
# API health / static assets
# ---------------------------------------------------------------------------
def test_health(web_server: str) -> None:
    status, headers, body = _http("GET", web_server + "/api/health")
    assert status == 200
    assert "application/json" in (_header(headers, "Content-Type") or "")
    data = _json(body)
    assert data == {
        "ok": True,
        "version": data["version"],
        "service": "bmp2dxf",
    }
    assert isinstance(data["version"], str) and data["version"]


def test_index_page(web_server: str) -> None:
    status, headers, body = _http("GET", web_server + "/")
    assert status == 200
    content_type = _header(headers, "Content-Type") or ""
    assert "text/html" in content_type
    html = body.decode("utf-8")
    assert "bmp2dxf" in html
    assert "/static/app.js" in html
    assert 'lang="zh-CN"' in html
    assert 'data-mode="color"' in html
    assert 'id="langToggle"' in html
    assert "/static/i18n.js" in html
    assert html.index("/static/i18n.js") < html.index("/static/app.js")


def test_static_assets(web_server: str) -> None:
    status, headers, body = _http("GET", web_server + "/static/app.js")
    assert status == 200
    assert "javascript" in (_header(headers, "Content-Type") or "")
    assert _header(headers, "Cache-Control")
    assert len(body) > 100

    status, headers, body = _http("GET", web_server + "/static/style.css")
    assert status == 200
    assert "text/css" in (_header(headers, "Content-Type") or "")
    assert len(body) > 100

    status, headers, body = _http("GET", web_server + "/static/i18n.js")
    assert status == 200
    assert "javascript" in (_header(headers, "Content-Type") or "")
    i18n = body.decode("utf-8")
    assert "bmp2dxf.lang" in i18n
    assert "langToggle" in i18n


def test_static_unknown_file_is_404_json(web_server: str) -> None:
    status, _headers, body = _http("GET", web_server + "/static/does-not-exist.js")
    assert status == 404
    assert _json(body)["ok"] is False


# ---------------------------------------------------------------------------
# Conversion API
# ---------------------------------------------------------------------------
def test_convert_success(conversion: dict) -> None:
    data = conversion
    assert data["ok"] is True
    assert isinstance(data["job_id"], str) and data["job_id"]
    assert "<svg" in data["svg"]
    assert data["mode_used"] in {"centerline", "outline"}
    assert isinstance(data["auto_reason"], str)
    assert data["source_width"] == 400
    assert data["source_height"] == 300
    stats = data["stats"]
    assert stats["path_count"] > 0
    assert stats["point_count"] > 0
    assert stats["source_width"] == 400
    assert stats["source_height"] == 300
    assert stats["work_width"] >= 400
    assert stats["duration_ms"] > 0
    assert isinstance(data["warnings"], list)
    assert data["downloads"]["dxf"] == f"/api/download/{data['job_id']}.dxf"
    assert data["downloads"]["svg"] == f"/api/download/{data['job_id']}.svg"


def test_convert_outline_mode(web_server: str) -> None:
    payload = _convert_payload(options={"mode": "outline", "precision": 85})
    status, _headers, body = _http("POST", web_server + "/api/convert", payload)
    assert status == 200, body.decode("utf-8", "replace")
    data = _json(body)
    assert data["ok"] is True
    assert data["mode_used"] == "outline"
    assert data["stats"]["path_count"] > 0
    assert data["stats"]["closed_path_count"] > 0


def test_convert_color_mode(web_server: str) -> None:
    png = to_png(color_art_image(420, 280))
    payload = _convert_payload(
        image_base64=base64.b64encode(png).decode("ascii"),
        filename="colour_art.png",
        options={"mode": "auto", "precision": 70},
    )
    status, _headers, body = _http("POST", web_server + "/api/convert", payload)
    assert status == 200, body.decode("utf-8", "replace")
    data = _json(body)
    assert data["ok"] is True
    assert data["mode_used"] == "color"
    assert data["stats"]["path_count"] > 0
    assert "<svg" in data["svg"]


def test_download_dxf_is_valid(web_server: str, conversion: dict) -> None:
    url = web_server + conversion["downloads"]["dxf"]
    status, headers, body = _http("GET", url)
    assert status == 200
    content_type = (_header(headers, "Content-Type") or "").lower()
    assert "dxf" in content_type
    disposition = _header(headers, "Content-Disposition") or ""
    assert "attachment" in disposition.lower()
    assert ".dxf" in disposition
    text = body.decode("utf-8")
    assert "SECTION" in text
    document = ezdxf.read(io.StringIO(text))
    entities = list(document.modelspace())
    assert len(entities) > 0
    layer_names = {entity.dxf.layer for entity in entities}
    assert layer_names & {"CENTERLINE", "OUTLINE"}


def test_download_svg(web_server: str, conversion: dict) -> None:
    url = web_server + conversion["downloads"]["svg"]
    status, headers, body = _http("GET", url)
    assert status == 200
    assert "image/svg+xml" in (_header(headers, "Content-Type") or "")
    assert "attachment" in (
        _header(headers, "Content-Disposition") or ""
    ).lower()
    svg = body.decode("utf-8")
    assert "<svg" in svg
    assert "<path" in svg
    assert 'viewBox="0 0 400 300"' in svg


# ---------------------------------------------------------------------------
# Invalid requests
# ---------------------------------------------------------------------------
def test_convert_rejects_invalid_json(web_server: str) -> None:
    status, headers, body = _http(
        "POST", web_server + "/api/convert", b"{this is not json"
    )
    assert status == 400
    assert "application/json" in (_header(headers, "Content-Type") or "")
    data = _json(body)
    assert data["ok"] is False
    assert data["error"]


def test_convert_rejects_missing_image(web_server: str) -> None:
    status, _headers, body = _http(
        "POST", web_server + "/api/convert", {"filename": "x.png"}
    )
    assert status == 400
    assert "image_base64" in _json(body)["error"]


def test_convert_rejects_bad_base64(web_server: str) -> None:
    status, _headers, body = _http(
        "POST",
        web_server + "/api/convert",
        {"image_base64": "!!!not-base64!!!", "filename": "x.png"},
    )
    assert status == 400
    assert _json(body)["ok"] is False


def test_convert_rejects_non_image_bytes(web_server: str) -> None:
    payload = {
        "image_base64": base64.b64encode(b"definitely not an image").decode("ascii"),
        "filename": "fake.png",
    }
    status, _headers, body = _http("POST", web_server + "/api/convert", payload)
    assert status == 400
    data = _json(body)
    assert data["ok"] is False
    assert "图片" in data["error"] or "格式" in data["error"]


def test_convert_rejects_bad_options(web_server: str) -> None:
    payload = _convert_payload(options={"mode": "not-a-mode"})
    status, _headers, body = _http("POST", web_server + "/api/convert", payload)
    assert status == 400
    data = _json(body)
    assert data["ok"] is False
    assert "参数" in data["error"]


def test_download_unknown_job_is_404_json(web_server: str) -> None:
    status, headers, body = _http(
        "GET", web_server + "/api/download/0123456789abcdef0123456789abcdef.dxf"
    )
    assert status == 404
    assert "application/json" in (_header(headers, "Content-Type") or "")
    assert _json(body)["ok"] is False


def test_unknown_api_is_404_json(web_server: str) -> None:
    status, _headers, body = _http("GET", web_server + "/api/does-not-exist")
    assert status == 404
    assert _json(body)["ok"] is False


def test_post_to_get_only_api_is_405(web_server: str) -> None:
    status, headers, body = _http("POST", web_server + "/api/health", {})
    assert status == 405
    assert "GET" in (_header(headers, "Allow") or "")
    assert _json(body)["ok"] is False


# ---------------------------------------------------------------------------
# Security: directory traversal
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "path",
    [
        "/samples/../bmp2dxf/pipeline.py",
        "/samples/%2e%2e%2fbmp2dxf%2fpipeline.py",
        "/samples/..%5c..%5cbmp2dxf%5cpipeline.py",
        "/samples/%2e%2e/%2e%2e/bmp2dxf/pipeline.py",
    ],
)
def test_samples_traversal_rejected(web_server: str, path: str) -> None:
    status, _headers, body = _http("GET", web_server + path)
    assert status in (400, 403, 404)
    text = body.decode("utf-8", "replace")
    assert "def convert" not in text
    assert "from __future__" not in text
    assert "Traceback" not in text


def test_static_traversal_rejected(web_server: str) -> None:
    status, _headers, body = _http("GET", web_server + "/static/../server.py")
    assert status in (400, 403, 404)
    assert "create_server" not in body.decode("utf-8", "replace")


def test_samples_listing(web_server: str) -> None:
    status, headers, body = _http("GET", web_server + "/api/samples")
    assert status == 200
    assert "application/json" in (_header(headers, "Content-Type") or "")
    data = _json(body)
    assert data["ok"] is True
    assert isinstance(data["samples"], list)
    for item in data["samples"]:
        assert {"name", "display_name", "url"} <= set(item)
        assert item["url"].startswith("/samples/")


# ---------------------------------------------------------------------------
# In-memory job cache and port errors
# ---------------------------------------------------------------------------
def _job(job_id: str) -> ConvertJob:
    return ConvertJob(
        job_id=job_id,
        created_at=time.time(),
        dxf=b"DXF",
        svg="<svg/>",
        source_name="sample.png",
        options={},
    )


def test_job_cache_evicts_oldest() -> None:
    cache = ConversionJobCache(max_jobs=2)
    cache.add(_job("a"))
    cache.add(_job("b"))
    cache.add(_job("c"))
    assert len(cache) == 2
    assert cache.get("a") is None
    assert cache.get("b") is not None
    assert cache.get("c") is not None


def test_job_cache_expires() -> None:
    cache = ConversionJobCache(max_jobs=4, ttl_seconds=0.05)
    cache.add(_job("short-lived"))
    time.sleep(0.1)
    assert cache.get("short-lived") is None


def test_port_in_use_raises_friendly_error(web_server: str) -> None:
    port = int(web_server.rsplit(":", 1)[1])
    with pytest.raises(PortInUseError) as excinfo:
        create_server(port=port)
    message = str(excinfo.value)
    assert "占用" in message
    assert str(port) in message
