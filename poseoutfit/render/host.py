from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Dict

from ..config import Config
from ..errors import RENDER_FAILED, SkillError
from .base import RenderProvider

DEFAULT_CAPABILITIES = {
    "supports_controlnet": False,
    "supports_negative_prompt": True,
    "supports_reference_images": True,
    "max_reference_images": 3,
    "accepts_local_files": True,
    "accepts_remote_urls": True,
    "sizes": ["768x1152", "1024x1536", "1024x1024", "1152x1536"],
    "max_n": 1,
}


class HostProvider(RenderProvider):
    """把渲染交给宿主：通过两条命令完成 submit 与 poll，Skill 不绑定具体服务商。

    环境变量：
      POSE_RENDER_COMMAND        接收 stdin JSON，返回 {"run_id": "..."}
      POSE_RENDER_POLL_COMMAND   接收 stdin {"run_id": "..."}，返回 {"status","images","error"}
      POSE_RENDER_CAPABILITIES   可选，JSON 覆盖 capabilities
      POSE_RENDER_TIMEOUT        可选，单次命令超时秒数，默认 120
    """

    name = "host"

    def __init__(self, config: Config) -> None:
        self.config = config

    def _command(self, name: str) -> str:
        value = os.environ.get(name, "").strip()
        if not value:
            raise SkillError(
                RENDER_FAILED,
                "未配置 %s，host 渲染器无法提交任务" % name,
                hint="设置 POSE_RENDERER=mock 或按 README 配置宿主渲染命令",
            )
        return value

    def _run(self, command: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        timeout = float(os.environ.get("POSE_RENDER_TIMEOUT", "120"))
        try:
            proc = subprocess.run(
                ["/bin/sh", "-c", command],
                input=json.dumps(payload, ensure_ascii=False),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise SkillError(RENDER_FAILED, "渲染命令超时", hint="稍后用同一 idempotency key 重试或查询原 run_id") from exc
        if proc.returncode != 0:
            raise SkillError(RENDER_FAILED, "渲染命令失败: %s" % (proc.stderr or "")[:500])
        try:
            result = json.loads(proc.stdout or "{}")
        except ValueError as exc:
            raise SkillError(RENDER_FAILED, "渲染命令返回的不是 JSON") from exc
        if not isinstance(result, dict):
            raise SkillError(RENDER_FAILED, "渲染命令返回结构不合法")
        return result

    def capabilities(self) -> Dict[str, Any]:
        raw = os.environ.get("POSE_RENDER_CAPABILITIES")
        if not raw:
            return dict(DEFAULT_CAPABILITIES)
        try:
            value = json.loads(raw)
        except ValueError as exc:
            raise SkillError(RENDER_FAILED, "POSE_RENDER_CAPABILITIES 不是合法 JSON") from exc
        merged = dict(DEFAULT_CAPABILITIES)
        merged.update(value)
        return merged

    def submit(self, spec: Dict[str, Any], assets: Dict[str, Any], idempotency_key: str) -> Dict[str, Any]:
        result = self._run(
            self._command("POSE_RENDER_COMMAND"),
            {"spec": spec, "assets": assets, "idempotency_key": idempotency_key},
        )
        run_id = result.get("run_id")
        if not run_id:
            raise SkillError(RENDER_FAILED, "渲染命令未返回 run_id")
        return {"run_id": str(run_id), "status": result.get("status", "RUNNING")}

    def poll(self, run_id: str) -> Dict[str, Any]:
        result = self._run(self._command("POSE_RENDER_POLL_COMMAND"), {"run_id": run_id})
        status = result.get("status")
        if status not in ("RUNNING", "COMPLETED", "FAILED"):
            raise SkillError(RENDER_FAILED, "轮询返回了未知状态: %r" % (status,))
        result["run_id"] = run_id
        return result
