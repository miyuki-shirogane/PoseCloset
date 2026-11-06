from __future__ import annotations

from typing import Any, Dict

from ..config import Config


class RenderProvider:
    name = "base"

    def capabilities(self) -> Dict[str, Any]:
        raise NotImplementedError

    def submit(self, spec: Dict[str, Any], assets: Dict[str, Any], idempotency_key: str) -> Dict[str, Any]:
        raise NotImplementedError

    def poll(self, run_id: str) -> Dict[str, Any]:
        raise NotImplementedError


def get_provider(config: Config) -> RenderProvider:
    if config.renderer == "host":
        from .host import HostProvider

        return HostProvider(config)
    if config.renderer == "mock":
        from .mock import MockProvider

        return MockProvider(config)
    raise ValueError("未知渲染器: %s" % config.renderer)
