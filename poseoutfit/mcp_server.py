from __future__ import annotations

import json
import sys
from typing import Any, Dict, Optional

from .config import Config
from .tool_specs import TOOL_SPECS
from .tools import Skill

PROTOCOL_VERSION = "2024-11-05"


class McpServer:
    def __init__(self, skill: Skill) -> None:
        self.skill = skill

    def handle(self, message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        method = message.get("method")
        message_id = message.get("id")
        if message_id is None:
            return None  # 通知不需要响应
        if method == "initialize":
            params = message.get("params") or {}
            return self._result(
                message_id,
                {
                    "protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "pose-outfit", "version": "0.2.0"},
                },
            )
        if method == "ping":
            return self._result(message_id, {})
        if method == "tools/list":
            return self._result(message_id, {"tools": TOOL_SPECS})
        if method == "tools/call":
            params = message.get("params") or {}
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if not isinstance(name, str):
                return self._error(message_id, -32602, "缺少工具名")
            envelope = self.skill.call(name, arguments)
            return self._result(
                message_id,
                {
                    "content": [{"type": "text", "text": json.dumps(envelope, ensure_ascii=False)}],
                    "isError": not envelope.get("ok", False),
                },
            )
        return self._error(message_id, -32601, "未知方法: %s" % method)

    @staticmethod
    def _result(message_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": message_id, "result": result}

    @staticmethod
    def _error(message_id: Any, code: int, message: str) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": message_id, "error": {"code": code, "message": message}}


def serve(config: Optional[Config] = None) -> None:
    skill = Skill(config or Config.from_env())
    server = McpServer(skill)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            continue
        response = server.handle(message)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
