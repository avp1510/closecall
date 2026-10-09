#!/usr/bin/env python3
"""CloseCall's small VSS proxy and static file server.

The server keeps team credentials and the VSS bearer token off the browser. It
uses only Python's standard library so it can run from a Kubernetes ConfigMap.
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
PUBLIC = ROOT / "public"
PORT = int(os.environ.get("PORT", "8080"))
VSS_URL = os.environ.get("VSS_URL", os.environ.get("INGRESS_URL", "")).rstrip("/")
VSS_USERNAME = os.environ.get("VSS_USERNAME", os.environ.get("USERNAME", ""))
VSS_PASSWORD = os.environ.get("VSS_PASSWORD", os.environ.get("PASSWORD", ""))
DEFAULT_QUERY = "first person view from a bicycle, handlebars visible, riding along a street"
VEHICLE_LABELS = ("car", "truck", "bus", "motorcycle", "bicycle", "person")

_token = ""
_token_time = 0.0


def request_vss(
    path: str,
    *,
    method: str = "GET",
    payload: Any | None = None,
    headers: dict[str, str] | None = None,
    authenticate: bool = True,
) -> tuple[int, dict[str, str], bytes]:
    if not VSS_URL:
        raise RuntimeError("VSS_URL is not configured")

    request_headers = {"Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    if authenticate:
        request_headers["Authorization"] = f"Bearer {get_token()}"

    body = None
    if payload is not None:
        body = json.dumps(payload).encode()
        request_headers["Content-Type"] = "application/json"

    request = urllib.request.Request(
        f"{VSS_URL}{path}", data=body, headers=request_headers, method=method
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


def get_token(force: bool = False) -> str:
    global _token, _token_time
    if _token and not force and time.time() - _token_time < 45 * 60:
        return _token
    if not VSS_USERNAME or not VSS_PASSWORD:
        raise RuntimeError("VSS_USERNAME and VSS_PASSWORD are not configured")

    status, _, body = request_vss(
        "/api/v1/auth/login",
        method="POST",
        payload={"username": VSS_USERNAME, "password": VSS_PASSWORD},
        authenticate=False,
    )
    if status >= 400:
        raise RuntimeError(f"VSS login failed ({status})")
    data = json.loads(body)
    _token = data["access_token"]
    _token_time = time.time()
    return _token


def iter_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from iter_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_dicts(child)


def event_from_evidence(payload: dict[str, Any]) -> dict[str, Any]:
    """Create a conservative event without inventing detections."""
    caption = str(payload.get("caption") or "")
    detections = payload.get("detections") or {}
    caption_lower = caption.lower()

    labels: list[str] = []
    for item in iter_dicts(detections):
        label = str(
            item.get("label")
            or item.get("class_name")
            or item.get("class")
            or item.get("name")
            or ""
        ).lower()
        if label in VEHICLE_LABELS and label not in labels:
            labels.append(label)

    evidence_label = next((label for label in labels if label in caption_lower), None)
    proximity_words = (
        "close",
        "near",
        "approach",
        "passing",
        "passes",
        "entering",
        "crossing",
        "opening",
    )
    is_close = any(word in caption_lower for word in proximity_words)
    side = "left" if "left" in caption_lower else "right" if "right" in caption_lower else "ahead"

    if "left" in caption_lower and is_close:
        corridor = "shift_right"
    elif "right" in caption_lower and is_close:
        corridor = "shift_left"
    elif is_close:
        corridor = "slow"
    else:
        corridor = "center"

    avoid = []
    if evidence_label and is_close:
        avoid.append(
            {
                "label": evidence_label,
                "side": side,
                "reason": (
                    f"The caption describes a nearby {evidence_label}; "
                    "the same class exists in stored detections."
                ),
            }
        )

    return {
        "clip_id": payload.get("clip_id") or payload.get("source") or "selected-clip",
        "camera_id": payload.get("camera_id") or "unknown",
        "start_s": float(payload.get("start_s") or 0),
        "end_s": float(payload.get("end_s") or 0),
        "summary": caption or "No caption was available for this segment.",
        "corridor": corridor,
        "avoid": avoid,
        "confidence": "medium" if avoid else "low",
        "generated_by": "evidence-rules",
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "CloseCall/1.0"

    def log_message(self, format_string: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format_string % args}", flush=True)

    def send_bytes(
        self,
        status: int,
        body: bytes,
        content_type: str,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def send_json(self, status: int, value: Any) -> None:
        self.send_bytes(status, json.dumps(value).encode(), "application/json")

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/health":
            self.send_json(
                200,
                {
                    "ok": True,
                    "vss_configured": bool(VSS_URL and VSS_USERNAME and VSS_PASSWORD),
                },
            )
            return
        if parsed.path == "/api/metadata/schema":
            self.proxy_json("/api/v1/metadata/schema")
            return
        if parsed.path == "/api/detections":
            query = urllib.parse.parse_qs(parsed.query)
            source = (query.get("source") or [""])[0]
            if not source:
                self.send_json(400, {"error": "source is required"})
                return
            self.proxy_json(
                "/api/v1/videos/detections?source="
                + urllib.parse.quote(source, safe="")
            )
            return
        if parsed.path == "/api/video":
            query = urllib.parse.parse_qs(parsed.query)
            source = (query.get("source") or [""])[0]
            if not source:
                self.send_json(400, {"error": "source is required"})
                return
            self.proxy_video(source)
            return
        self.serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/search":
            incoming = self.read_json()
            query = str(incoming.get("query") or DEFAULT_QUERY)
            body = {
                "query": query,
                "top_k": min(max(int(incoming.get("top_k") or 8), 1), 20),
                "llm_top_n": 3,
                "min_similarity": float(incoming.get("min_similarity") or 0.2),
                "metadata_filters": incoming.get("metadata_filters") or {},
                "include_public": True,
            }
            self.proxy_json("/api/v1/search", method="POST", payload=body)
            return
        if parsed.path == "/api/event":
            self.send_json(200, event_from_evidence(self.read_json()))
            return
        self.send_json(404, {"error": "not found"})

    def proxy_json(
        self, path: str, *, method: str = "GET", payload: Any | None = None
    ) -> None:
        try:
            status, headers, body = request_vss(path, method=method, payload=payload)
            if status == 401:
                get_token(force=True)
                status, headers, body = request_vss(path, method=method, payload=payload)
            self.send_bytes(
                status,
                body,
                headers.get("Content-Type", "application/json"),
            )
        except Exception as error:
            self.send_json(502, {"error": str(error)})

    def proxy_video(self, source: str) -> None:
        try:
            token = get_token()
            query = urllib.parse.urlencode({"source": source, "token": token})
            url = f"{VSS_URL}/api/v1/videos/stream?{query}"
            headers = {}
            if self.headers.get("Range"):
                headers["Range"] = self.headers["Range"]
            request = urllib.request.Request(url, headers=headers)
            try:
                response = urllib.request.urlopen(request, timeout=120)
            except urllib.error.HTTPError as error:
                response = error

            self.send_response(response.status)
            for key in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"):
                if response.headers.get(key):
                    self.send_header(key, response.headers[key])
            self.send_header("Cache-Control", "private, max-age=300")
            self.end_headers()
            while chunk := response.read(64 * 1024):
                self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception as error:
            self.send_json(502, {"error": str(error)})

    def serve_static(self, request_path: str) -> None:
        relative = request_path.lstrip("/") or "index.html"
        if ".." in Path(relative).parts:
            self.send_json(400, {"error": "invalid path"})
            return
        path = PUBLIC / relative
        if not path.is_file():
            path = PUBLIC / "index.html"
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_bytes(200, path.read_bytes(), content_type)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"CloseCall listening on 0.0.0.0:{PORT}", flush=True)
    server.serve_forever()
