from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional

from .assets import is_safe_asset_path, resolve_asset_url
from .config import (
    ALLOWED_OUTFIT_CATEGORIES,
    ALLOWED_POSE_SYSTEMS,
    OUTFIT_CATEGORIES,
    POSE_CATEGORIES,
)
from .errors import LIBRARY_UNAVAILABLE, SkillError

SCHEMA_VERSION = 1

POSE_KEYS = {
    "id", "code", "category", "subcategory", "label", "people", "angle",
    "thumbnail", "ref_image", "control_type", "prompt_snippet", "source",
    "source_url", "author", "license", "commercial_use", "mirror_allowed", "enabled",
}
OUTFIT_KEYS = {
    "id", "category", "label", "keywords", "thumbnail", "ref_image", "source",
    "source_url", "author", "license", "commercial_use", "mirror_allowed", "enabled",
}


def _bad(message: str) -> SkillError:
    return SkillError(LIBRARY_UNAVAILABLE, message)


def _check_category(item: dict, kind: str) -> dict:
    category = item.get("category")
    if not isinstance(category, dict) or set(category) != {"id", "name", "order"}:
        raise _bad("category 结构不合法")
    allowed = POSE_CATEGORIES if kind == "pose" else OUTFIT_CATEGORIES
    cid = category["id"]
    if cid not in allowed:
        raise _bad("分类不在白名单: %r" % (cid,))
    if category["name"] != allowed[cid]["name"] or category["order"] != allowed[cid]["order"]:
        raise _bad("分类定义与白名单不一致: %r" % (cid,))
    return category


def _check_asset(item: dict, kind: str, where: str) -> None:
    for field in ("thumbnail", "ref_image"):
        rel = item.get(field)
        if not isinstance(rel, str) or not is_safe_asset_path(kind, rel):
            raise _bad("%s 的 %s 路径不合法" % (where, field))
    expected = resolve_asset_url(kind, item["ref_image"])
    if item.get("source_url") != expected:
        raise _bad("%s 的 source_url 与索引路径不一致" % where)
    if not item.get("license") or not item.get("author") or not item.get("source"):
        raise _bad("%s 缺少授权元数据" % where)
    if item.get("mirror_allowed") is not False:
        raise _bad("%s 必须标记 mirror_allowed=false" % where)
    if item.get("enabled") is not True:
        raise _bad("%s 必须显式 enabled=true" % where)


def _check_pose(item: dict) -> None:
    if set(item) != POSE_KEYS:
        extra = set(item) - POSE_KEYS
        missing = POSE_KEYS - set(item)
        raise _bad("pose 字段不合法 extra=%s missing=%s" % (sorted(extra), sorted(missing)))
    if not isinstance(item["id"], str) or not item["id"]:
        raise _bad("pose id 不合法")
    if item["people"] != 1:
        raise _bad("pose 仅允许单人")
    if item["commercial_use"] is not False:
        raise _bad("pose 必须标记 commercial_use=false")
    if not str(item["prompt_snippet"]).strip():
        raise _bad("pose 缺少 prompt_snippet")
    _check_category(item, "pose")
    _check_asset(item, "pose", "pose:%s" % item["id"])


def _check_outfit(item: dict) -> None:
    if set(item) != OUTFIT_KEYS:
        extra = set(item) - OUTFIT_KEYS
        missing = OUTFIT_KEYS - set(item)
        raise _bad("outfit 字段不合法 extra=%s missing=%s" % (sorted(extra), sorted(missing)))
    if not isinstance(item["id"], str) or not item["id"]:
        raise _bad("outfit id 不合法")
    if item["commercial_use"] is not True:
        raise _bad("outfit 必须标记 commercial_use=true")
    if not str(item["keywords"]).strip():
        raise _bad("outfit 缺少 keywords")
    _check_category(item, "outfit")
    _check_asset(item, "outfit", "outfit:%s" % item["id"])


class Library:
    def __init__(self, poses: List[dict], outfits: List[dict]) -> None:
        self.poses = poses
        self.outfits = outfits
        self._poses_by_id = {item["id"]: item for item in poses}
        self._outfits_by_id = {item["id"]: item for item in outfits}

    @classmethod
    def load(cls, path: Path) -> "Library":
        try:
            raw = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise _bad("索引读取失败: %s" % exc) from exc
        if not isinstance(raw, dict) or set(raw) != {"schema_version", "poses", "outfits"}:
            raise _bad("索引顶层字段不合法")
        if raw["schema_version"] != SCHEMA_VERSION:
            raise _bad("不支持的 schema_version")
        poses = raw["poses"]
        outfits = raw["outfits"]
        if not isinstance(poses, list) or not isinstance(outfits, list):
            raise _bad("poses/outfits 必须是数组")
        seen = set()
        for item in poses:
            if not isinstance(item, dict):
                raise _bad("pose 条目必须是对象")
            _check_pose(item)
            if item["id"] in seen:
                raise _bad("重复 id: %s" % item["id"])
            seen.add(item["id"])
        for item in outfits:
            if not isinstance(item, dict):
                raise _bad("outfit 条目必须是对象")
            _check_outfit(item)
            if item["id"] in seen:
                raise _bad("重复 id: %s" % item["id"])
            seen.add(item["id"])
        return cls(poses, outfits)

    def categories(self, kind: str) -> List[dict]:
        allowed = POSE_CATEGORIES if kind == "pose" else OUTFIT_CATEGORIES
        items = self.poses if kind == "pose" else self.outfits
        counts: Dict[str, int] = {}
        for item in items:
            counts[item["category"]["id"]] = counts.get(item["category"]["id"], 0) + 1
        result = []
        for cid, meta in allowed.items():
            category_items = [item for item in items if item["category"]["id"] == cid]
            count = len(category_items)
            if count == 0:
                continue
            entry = {"id": cid, "name": meta["name"], "count": count, "order": meta["order"]}
            if kind == "pose":
                sub = Counter(item["subcategory"] for item in category_items)
                entry["subcategories"] = [
                    {"name": name, "count": value}
                    for name, value in sorted(sub.items(), key=lambda pair: (-pair[1], pair[0]))
                ]
            result.append(entry)
        return sorted(result, key=lambda x: x["order"])

    def items(self, kind: str, category_id: str) -> List[dict]:
        items = self.poses if kind == "pose" else self.outfits
        return [item for item in items if item["category"]["id"] == category_id]

    def get(self, kind: str, item_id: str) -> Optional[dict]:
        table = self._poses_by_id if kind == "pose" else self._outfits_by_id
        return table.get(item_id)

    def category_allowed(self, kind: str, category_id: str) -> bool:
        allowed = ALLOWED_POSE_SYSTEMS if kind == "pose" else ALLOWED_OUTFIT_CATEGORIES
        return category_id in allowed
