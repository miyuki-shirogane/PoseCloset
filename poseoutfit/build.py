from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .assets import resolve_asset_url
from .config import (
    ALLOWED_OUTFIT_CATEGORIES,
    ALLOWED_POSE_SYSTEMS,
    ASSET_ORIGINS,
    OUTFIT_CATEGORIES,
    POSE_CATEGORIES,
)
from .errors import LIBRARY_UNAVAILABLE, SkillError

SCHEMA_VERSION = 1

POSE_SYSTEM_EN = {"full": "full body shot", "bust": "upper body portrait"}

POSE_CATEGORY_EN = {
    "可爱系": "cute playful pose",
    "坐姿": "sitting pose",
    "站姿": "standing pose",
    "跪立": "kneeling pose",
    "趴卧": "lying prone pose",
    "侧坐・女孩坐": "side sitting pose with legs to one side",
    "蹲姿": "squatting pose",
    "前倾": "leaning forward pose",
    "后仰・挺背": "leaning back with arched posture",
    "扭身": "twisted torso pose",
}

POSE_AUTHOR = "ギア"
POSE_SOURCE = "pose-gallery-anhao"
POSE_LICENSE = "upstream-noncommercial"
OUTFIT_SOURCE = "costume-db-01"
OUTFIT_LICENSE = "reference-only"


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def _pick_view(views: List[dict]) -> Optional[dict]:
    for view in views:
        if view.get("angleId") == "front" and view.get("thumb") and view.get("full"):
            return view
    for view in views:
        if view.get("thumb") and view.get("full"):
            return view
    return None


def build_index(
    pose_catalog: dict,
    costume_catalog: dict,
    generated_at: Optional[str] = None,
) -> Tuple[dict, dict]:
    """把上游 catalog 转成本 Skill 的索引；成人向与白名单外条目在此彻底丢弃。"""
    poses: List[dict] = []
    excluded = {"pose_outside_allowlist": 0, "pose_adult": 0, "pose_pair": 0, "pose_unknown_category": 0}
    for item in pose_catalog.get("poses", []):
        system_id = item.get("systemId")
        if system_id not in ALLOWED_POSE_SYSTEMS:
            excluded["pose_outside_allowlist"] += 1
            continue
        if item.get("adult") is not False:
            excluded["pose_adult"] += 1
            continue
        if item.get("people") != 1:
            excluded["pose_pair"] += 1
            continue
        view = _pick_view(item.get("views") or [])
        mapping = POSE_CATEGORY_EN.get(item.get("category"))
        if mapping is None or view is None or not item.get("id") or not item.get("name"):
            excluded["pose_unknown_category"] += 1
            continue
        category = POSE_CATEGORIES[system_id]
        poses.append(
            {
                "id": item["id"],
                "code": item.get("code", ""),
                "category": {"id": system_id, "name": category["name"], "order": category["order"]},
                "subcategory": item["category"],
                "label": item["name"],
                "people": 1,
                "angle": view.get("angleId", "front"),
                "thumbnail": view["thumb"],
                "ref_image": view["full"],
                "control_type": "lineart",
                "prompt_snippet": "%s, %s" % (POSE_SYSTEM_EN[system_id], mapping),
                "source": POSE_SOURCE,
                "source_url": resolve_asset_url("pose", view["full"]),
                "author": POSE_AUTHOR,
                "license": POSE_LICENSE,
                "commercial_use": False,
                "mirror_allowed": False,
                "enabled": True,
            }
        )

    outfits: List[dict] = []
    excluded.update({"outfit_outside_allowlist": 0, "outfit_adult": 0, "outfit_incomplete": 0})
    for item in costume_catalog.get("costumes", []):
        category_id = item.get("category")
        if category_id not in ALLOWED_OUTFIT_CATEGORIES:
            excluded["outfit_outside_allowlist"] += 1
            continue
        if item.get("adult") is not False:
            excluded["outfit_adult"] += 1
            continue
        if not item.get("id") or not item.get("thumb") or not item.get("preview") or not item.get("keywords"):
            excluded["outfit_incomplete"] += 1
            continue
        category = OUTFIT_CATEGORIES[category_id]
        outfits.append(
            {
                "id": item["id"],
                "category": {"id": category_id, "name": category["name"], "order": category["order"]},
                "label": "%s %s" % (category["name"], item["id"]),
                "keywords": item["keywords"],
                "thumbnail": item["thumb"],
                "ref_image": item["preview"],
                "source": OUTFIT_SOURCE,
                "source_url": resolve_asset_url("outfit", item["preview"]),
                "author": POSE_AUTHOR,
                "license": OUTFIT_LICENSE,
                "commercial_use": True,
                "mirror_allowed": False,
                "enabled": True,
            }
        )

    if not poses or not outfits:
        raise SkillError(LIBRARY_UNAVAILABLE, "过滤后素材为空，拒绝生成索引")

    index = {"schema_version": SCHEMA_VERSION, "poses": poses, "outfits": outfits}
    meta = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at or _now_iso(),
        "sources": {
            "poses": {
                "catalog": pose_catalog.get("source"),
                "origin": ASSET_ORIGINS["pose"],
                "upstream": pose_catalog.get("upstream"),
                "author": POSE_AUTHOR,
                "license": POSE_LICENSE,
                "commercial_use": False,
                "mirror_allowed": False,
                "note": "上游说明姿势线稿不得用于商业用途，本索引仅保存编号、名称与公开路径。",
            },
            "outfits": {
                "catalog": costume_catalog.get("source"),
                "origin": ASSET_ORIGINS["outfit"],
                "author": POSE_AUTHOR,
                "license": OUTFIT_LICENSE,
                "commercial_use": True,
                "mirror_allowed": False,
                "note": "允许作为创作参考，禁止再分发、转载或转售图像数据本身。",
            },
        },
        "allowed_categories": {
            "poses": sorted(ALLOWED_POSE_SYSTEMS),
            "outfits": sorted(ALLOWED_OUTFIT_CATEGORIES),
        },
        "kept": {"poses": len(poses), "outfits": len(outfits)},
        "excluded": excluded,
        "upstream_counts": {
            "poses": pose_catalog.get("poseCount"),
            "pose_views": pose_catalog.get("viewCount"),
            "outfits": costume_catalog.get("total"),
        },
    }
    return index, meta


def write_index(index: dict, meta: dict, index_path: Path, meta_path: Path) -> None:
    index_path = Path(index_path)
    meta_path = Path(meta_path)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
