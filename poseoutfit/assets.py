from __future__ import annotations

import re
from collections import OrderedDict
from typing import Callable, Dict, Optional, Tuple
from urllib.request import Request, urlopen

from .config import ASSET_ORIGINS, Config
from .errors import ASSET_PATH_BLOCKED, ASSET_UNREACHABLE, INVALID_INPUT, SkillError
from .security import sniff_image, validate_https_url

PATH_PATTERNS = {
    "pose": re.compile(r"^(?:thumbs|img)/[A-Za-z0-9_]+\.(?:jpg|png)$"),
    "outfit": re.compile(r"^(?:thumbs|img)/[A-Z]{3}-\d{4}\.webp$"),
}

_ALLOWED_HOSTS = {
    "pose": {ASSET_ORIGINS["pose"].split("://", 1)[1]},
    "outfit": {ASSET_ORIGINS["outfit"].split("://", 1)[1]},
}

Fetcher = Callable[[str, float, int], bytes]


def is_safe_asset_path(kind: str, rel: str) -> bool:
    pattern = PATH_PATTERNS.get(kind)
    if pattern is None or not isinstance(rel, str):
        return False
    if rel.startswith("/") or "\\" in rel or ".." in rel or "?" in rel or "#" in rel:
        return False
    return bool(pattern.match(rel))


def resolve_asset_url(kind: str, rel: str) -> str:
    if not is_safe_asset_path(kind, rel):
        raise SkillError(ASSET_PATH_BLOCKED, "素材路径不合法: %r" % (rel,))
    url = "%s/%s" % (ASSET_ORIGINS[kind], rel)
    validate_https_url(url, allowed_hosts=_ALLOWED_HOSTS[kind], resolve_dns=False)
    return url


def _default_fetch(url: str, timeout: float, max_bytes: int) -> bytes:
    request = Request(url, headers={"User-Agent": "pose-outfit-skill/1.0"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 - https enforced above
        final_url = response.geturl()
        validate_https_url(final_url, allowed_hosts=_ALLOWED_HOSTS[_kind_of(url)], resolve_dns=True)
        data = response.read(max_bytes + 1)
    if len(data) > max_bytes:
        raise SkillError(ASSET_UNREACHABLE, "素材超过大小上限")
    if sniff_image(data) is None:
        raise SkillError(ASSET_UNREACHABLE, "素材不是可识别的图片")
    return data


def _kind_of(url: str) -> str:
    host = url.split("://", 1)[1].split("/", 1)[0].lower()
    for kind, hosts in _ALLOWED_HOSTS.items():
        if host in hosts:
            return kind
    raise SkillError(ASSET_PATH_BLOCKED, "未知素材域名")


class AssetResolver:
    """只在内存中缓存字节，绝不写盘；用于按需取图与校验。"""

    def __init__(self, config: Config, fetcher: Optional[Fetcher] = None, cache_items: int = 80) -> None:
        self.config = config
        self.fetcher = fetcher or _default_fetch
        self.cache_items = cache_items
        self._cache: "OrderedDict[Tuple[str, str], bytes]" = OrderedDict()

    def url(self, kind: str, rel: str) -> str:
        return resolve_asset_url(kind, rel)

    def fetch(self, kind: str, rel: str) -> bytes:
        url = self.url(kind, rel)
        key = (kind, rel)
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key]
        try:
            data = self.fetcher(url, self.config.asset_timeout, self.config.asset_max_bytes)
        except SkillError:
            raise
        except Exception as exc:  # 网络、超时、证书等
            raise SkillError(ASSET_UNREACHABLE, "素材站暂时读不到: %s" % exc) from exc
        if len(data) > self.config.asset_max_bytes:
            raise SkillError(ASSET_UNREACHABLE, "素材超过大小上限")
        if sniff_image(data) is None:
            raise SkillError(ASSET_UNREACHABLE, "素材不是可识别的图片")
        self._cache[key] = data
        while len(self._cache) > self.cache_items:
            self._cache.popitem(last=False)
        return data


def fetch_public_image(url: str, timeout: float, max_bytes: int) -> bytes:
    """下载用户提供的公网图片（主体参考），带 SSRF 防护与大小限制。"""
    validate_https_url(url, resolve_dns=True)
    request = Request(url, headers={"User-Agent": "pose-outfit-skill/1.0"})
    try:
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - https enforced above
            validate_https_url(response.geturl(), resolve_dns=True)
            data = response.read(max_bytes + 1)
    except SkillError:
        raise
    except Exception as exc:
        raise SkillError(INVALID_INPUT, "主体图片下载失败: %s" % exc) from exc
    if len(data) > max_bytes:
        raise SkillError(INVALID_INPUT, "主体图片超过大小上限")
    if sniff_image(data) is None:
        raise SkillError(INVALID_INPUT, "主体图片不是可识别的图片")
    return data
