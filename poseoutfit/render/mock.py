from __future__ import annotations

import base64
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict
from xml.sax.saxutils import escape

from ..config import Config
from .base import RenderProvider


def _size(spec: Dict[str, Any]) -> tuple:
    raw = str(spec.get("size") or "1024x1536")
    try:
        width, height = raw.lower().split("x")
        return int(width), int(height)
    except ValueError:
        return 1024, 1536


def _placeholder_svg(spec: Dict[str, Any], assets: Dict[str, Any]) -> str:
    width, height = _size(spec)
    pose = (assets.get("pose") or {}).get("id", "-")
    outfit = (assets.get("outfit") or {}).get("id", "未选服装")
    subject = (assets.get("subject") or {}).get("kind", "none")
    lines = [
        ("MOCK RENDER", 48),
        ("pose: %s" % pose, 28),
        ("outfit: %s" % outfit, 28),
        ("subject: %s" % subject, 28),
        ("%dx%d" % (width, height), 24),
    ]
    body = []
    y = height // 3
    for text, size in lines:
        body.append(
            '<text x="50%%" y="%d" fill="#e8eef7" font-family="Helvetica,Arial" font-size="%d" '
            'text-anchor="middle">%s</text>' % (y, size, escape(str(text)[:60]))
        )
        y += size + 28
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">'
        '<rect width="100%%" height="100%%" fill="#1c2430"/>%s</svg>'
    ) % (width, height, width, height, "".join(body))


class MockProvider(RenderProvider):
    name = "mock"

    def __init__(self, config: Config, delay_seconds: float = 1.0) -> None:
        self.config = config
        self.delay_seconds = delay_seconds
        self.dir = Path(config.state_dir) / "mock"
        self.dir.mkdir(parents=True, exist_ok=True)

    def capabilities(self) -> Dict[str, Any]:
        return {
            "supports_controlnet": False,
            "supports_negative_prompt": True,
            "supports_reference_images": True,
            "max_reference_images": 3,
            "accepts_local_files": True,
            "accepts_remote_urls": True,
            "sizes": ["768x1152", "1024x1536", "1024x1024", "1152x1536"],
            "max_n": 1,
        }

    def _path(self, run_id: str) -> Path:
        safe = "".join(ch for ch in run_id if ch.isalnum() or ch in "-_")
        return self.dir / ("%s.json" % safe)

    def submit(self, spec: Dict[str, Any], assets: Dict[str, Any], idempotency_key: str) -> Dict[str, Any]:
        run_id = "mock-" + hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()[:12]
        path = self._path(run_id)
        if not path.exists():
            payload = {"run_id": run_id, "created_at": time.time(), "spec": spec, "assets": assets}
            path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return {"run_id": run_id, "status": "RUNNING"}

    def poll(self, run_id: str) -> Dict[str, Any]:
        path = self._path(run_id)
        if not path.exists():
            return {"run_id": run_id, "status": "FAILED", "error": {"code": "RENDER_FAILED", "message": "未知 run_id"}}
        payload = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - payload["created_at"] < self.delay_seconds:
            return {"run_id": run_id, "status": "RUNNING"}
        width, height = _size(payload["spec"])
        svg = _placeholder_svg(payload["spec"], payload.get("assets") or {})
        data_uri = "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")
        return {
            "run_id": run_id,
            "status": "COMPLETED",
            "images": [{"url": data_uri, "width": width, "height": height}],
        }
