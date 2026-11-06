from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import Config
from .tool_specs import TOOL_SPECS


def _read_args(raw: str) -> dict:
    try:
        value = json.loads(raw)
    except ValueError as exc:
        raise SystemExit("参数不是合法 JSON: %s" % exc)
    if not isinstance(value, dict):
        raise SystemExit("参数必须是 JSON 对象")
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="pose-outfit", description="pose + outfit 生图 Skill CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list-tools", help="输出工具定义（供模型/宿主注册）")

    call = sub.add_parser("call", help="调用一个工具")
    call.add_argument("name", help="工具名")
    call.add_argument("args", nargs="?", default="{}", help="JSON 参数")
    call.add_argument("--file", help="从文件读取 JSON 参数")

    sub.add_parser("serve", help="以 MCP stdio 方式启动（客户端自动拉起，不监听端口）")
    sub.add_parser("purge", help="清理过期会话")

    ns = parser.parse_args(argv)
    config = Config.from_env()

    if ns.command == "list-tools":
        print(json.dumps({"tools": TOOL_SPECS}, ensure_ascii=False, indent=2))
        return 0

    if ns.command == "serve":
        from .errors import SkillError
        from .mcp_server import serve

        try:
            serve(config)
        except SkillError as exc:
            print(json.dumps({"ok": False, "error": exc.to_dict()}, ensure_ascii=False), file=sys.stderr)
            return 1
        return 0

    if ns.command == "purge":
        from .session import SessionStore

        removed = SessionStore(config).purge_expired()
        print(json.dumps({"ok": True, "data": {"removed": removed}}, ensure_ascii=False))
        return 0

    raw = Path(ns.file).read_text(encoding="utf-8") if ns.file else ns.args
    args = _read_args(raw)

    from .errors import SkillError
    from .tools import Skill

    try:
        skill = Skill(config)
    except SkillError as exc:
        print(json.dumps({"ok": False, "error": exc.to_dict()}, ensure_ascii=False, indent=2))
        return 1
    envelope = skill.call(ns.name, args)
    print(json.dumps(envelope, ensure_ascii=False, indent=2))
    return 0 if envelope.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
