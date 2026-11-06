from __future__ import annotations

import ipaddress
import re
import socket
from pathlib import Path
from typing import Iterable, Optional, Tuple
from urllib.parse import urlparse

from .errors import ASSET_PATH_BLOCKED, INVALID_INPUT, SkillError

WEBP = "image/webp"
JPEG = "image/jpeg"
PNG = "image/png"
GIF = "image/gif"
BMP = "image/bmp"
TIFF = "image/tiff"

_MAGIC = (
    (b"\xff\xd8\xff", JPEG),
    (b"\x89PNG\r\n\x1a\n", PNG),
    (b"GIF87a", GIF),
    (b"GIF89a", GIF),
    (b"BM", BMP),
    (b"II*\x00", TIFF),
    (b"MM\x00*", TIFF),
)

ADULT_PATTERNS = (
    r"裸", r"露点", r"露乳", r"走光", r"性爱", r"做爱", r"色情", r"情色", r"成人向",
    r"情趣", r"内衣", r"内裤", r"泳装", r"比基尼", r"性感", r"撩人", r"床照", r"开房",
    r"乳头", r"下体", r"私处", r"丝袜诱惑", r"巨乳", r"爆乳",
    r"nsfw", r"nude", r"naked", r"porn", r"explicit", r"lingerie", r"swimsuit",
    r"bikini", r"sexy", r"erotic", r"fetish", r"topless", r"cleavage", r"hentai",
)

_INSTRUCTION_PATTERNS = (
    r"忽略(以上|之前|前面|所有)",
    r"无视(以上|之前|前面|所有)",
    r"ignore\s+(all\s+)?(previous|prior|above)",
    r"disregard\s+(all\s+)?(previous|prior|above)",
    r"system\s*prompt",
    r"你现在是",
    r"请扮演",
)

_ADULT_RE = re.compile("|".join(ADULT_PATTERNS), re.IGNORECASE)
_INSTRUCTION_RE = re.compile("|".join(_INSTRUCTION_PATTERNS), re.IGNORECASE)
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_MD_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_SPACE_RE = re.compile(r"\s+")

SUBJECT_MAX_CHARS = 300


def contains_adult(text: str) -> bool:
    return bool(text) and bool(_ADULT_RE.search(text))


def sanitize_subject_text(text: Optional[str]) -> str:
    if not text:
        return ""
    value = str(text)
    value = _CODE_FENCE_RE.sub(" ", value)
    value = _MD_LINK_RE.sub(r"\1", value)
    value = _URL_RE.sub(" ", value)
    value = _CONTROL_RE.sub(" ", value)
    value = value.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    value = _INSTRUCTION_RE.sub(" ", value)
    value = re.sub(r"[`*_#>\[\]{}|]+", " ", value)
    value = _SPACE_RE.sub(" ", value).strip()
    return value[:SUBJECT_MAX_CHARS]


def sniff_image(data: bytes) -> Optional[str]:
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return WEBP
    for magic, mime in _MAGIC:
        if data.startswith(magic):
            return mime
    return None


def strip_exif(data: bytes, mime: str) -> Tuple[bytes, bool]:
    """有 Pillow 时重编码去元数据；没有则原样返回并标记为未处理。"""
    try:
        from io import BytesIO

        from PIL import Image  # type: ignore
    except Exception:
        return data, False
    try:
        with Image.open(BytesIO(data)) as image:
            image.load()
            rgb = image.convert("RGB")
            out = BytesIO()
            fmt = "JPEG" if mime in (JPEG, WEBP, TIFF, BMP) else "PNG"
            rgb.save(out, format=fmt, quality=92) if fmt == "JPEG" else rgb.save(out, format=fmt)
            return out.getvalue(), True
    except Exception:
        return data, False


def read_subject_image(path: Path, max_bytes: int) -> Tuple[bytes, str, bool]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise SkillError(INVALID_INPUT, "读取主体图片失败: %s" % exc) from exc
    if not raw:
        raise SkillError(INVALID_INPUT, "主体图片为空")
    if len(raw) > max_bytes:
        raise SkillError(INVALID_INPUT, "主体图片超过 %d 字节上限" % max_bytes)
    mime = sniff_image(raw)
    if mime is None:
        raise SkillError(INVALID_INPUT, "主体图片不是可识别的 JPEG/PNG/WEBP/GIF/BMP/TIFF")
    cleaned, stripped = strip_exif(raw, mime)
    return cleaned, mime, stripped


def _host_is_public(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    if not infos:
        return False
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False
    return True


def validate_https_url(
    url: str, allowed_hosts: Optional[Iterable[str]] = None, resolve_dns: bool = False
) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise SkillError(ASSET_PATH_BLOCKED, "仅允许 https URL")
    host = parsed.hostname.lower()
    if allowed_hosts is not None and host not in {h.lower() for h in allowed_hosts}:
        raise SkillError(ASSET_PATH_BLOCKED, "域名不在白名单: %s" % host)
    if parsed.username or parsed.password or parsed.port not in (None, 443):
        raise SkillError(ASSET_PATH_BLOCKED, "URL 不允许包含凭据或自定义端口")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and (
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
        or ip.is_multicast or ip.is_unspecified
    ):
        raise SkillError(ASSET_PATH_BLOCKED, "拒绝内网、回环或保留地址")
    if resolve_dns and not _host_is_public(host):
        raise SkillError(ASSET_PATH_BLOCKED, "拒绝对内网、回环或保留地址发起请求")
    return url
