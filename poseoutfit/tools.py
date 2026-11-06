from __future__ import annotations

import hashlib
import inspect
import json
import random
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .assets import AssetResolver, fetch_public_image, resolve_asset_url
from .config import ASPECT_RATIOS, DEFAULT_SPEC, Config
from .errors import (
    ALREADY_COMPLETED,
    BATCH_EXHAUSTED,
    CATEGORY_EMPTY,
    INTERNAL_ERROR,
    INVALID_ID,
    INVALID_INPUT,
    INVALID_STATE,
    LIBRARY_UNAVAILABLE,
    LICENSE_BLOCKED,
    NOT_IN_BATCH,
    SkillError,
    fail,
    ok,
)
from .library import Library
from .prompt_builder import STYLE_ALIASES, STYLE_BUNDLES, accessory_tokens, build_prompts, normalize_style
from .render.base import RenderProvider, get_provider
from .security import BMP, GIF, JPEG, PNG, TIFF, WEBP, contains_adult, read_subject_image, sanitize_subject_text, sniff_image, strip_exif
from .session import SessionStore, require_state
from .state_machine import ALLOWED_ACTIONS, BACK_TARGETS
from .tool_specs import TOOL_NAMES

SIZE_BY_ASPECT = {
    "1:1": "1024x1024",
    "3:4": "1152x1536",
    "4:3": "1536x1152",
    "2:3": "1024x1536",
    "3:2": "1536x1024",
    "9:16": "864x1536",
    "16:9": "1536x864",
}

EXT_BY_MIME = {JPEG: ".jpg", PNG: ".png", WEBP: ".webp", GIF: ".gif", BMP: ".bmp", TIFF: ".tiff"}


class Skill:
    def __init__(
        self,
        config: Optional[Config] = None,
        library: Optional[Library] = None,
        store: Optional[SessionStore] = None,
        provider: Optional[RenderProvider] = None,
        resolver: Optional[AssetResolver] = None,
    ) -> None:
        self.config = config or Config.from_env()
        self.library = library or Library.load(self.config.index_path)
        self.store = store or SessionStore(self.config)
        self.provider = provider or get_provider(self.config)
        self.resolver = resolver or AssetResolver(self.config)
        if self.config.pose_library == "own":
            if any(item.get("source") == "pose-gallery-anhao" for item in self.library.poses):
                raise SkillError(
                    LIBRARY_UNAVAILABLE,
                    "POSE_LIBRARY=own 但索引仍包含上游姿势，请先替换为自有或已授权素材",
                )

    # ------------------------------------------------------------------ 调度
    def call(self, name: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if name not in TOOL_NAMES or not hasattr(self, name):
            return fail(SkillError(INVALID_ID, "未知工具: %s" % name))
        args = dict(args or {})
        try:
            inspect.signature(getattr(self, name)).bind(**args)
        except TypeError as exc:
            return fail(SkillError(INVALID_INPUT, "参数不合法: %s" % exc))
        try:
            return ok(getattr(self, name)(**args) or {})
        except SkillError as exc:
            return fail(exc)
        except Exception as exc:  # 不把堆栈暴露给模型
            return fail(SkillError(INTERNAL_ERROR, "%s: %s" % (type(exc).__name__, exc)))

    # ------------------------------------------------------------------ 会话
    def start_pose_task(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        data = self.store.create(user_id)
        return {"session_id": data["session_id"], "state": data["state"], "expires_at": int(data["expires_at"])}

    def get_session_state(self, session_id: str) -> Dict[str, Any]:
        data = self.store.read(session_id)
        return {
            "state": data["state"],
            "selections": {"pose_id": data.get("pose_id"), "outfit_id": data.get("outfit_id")},
            "batch": self._batch_summary(data),
            "subject": self._subject_summary(data.get("subject")),
            "spec": data.get("spec"),
            "risks": self._current_risks(data),
            "render": self._render_summary(data.get("render")),
            "allowed_actions": list(ALLOWED_ACTIONS.get(data["state"], [])),
            "expires_at": int(data["expires_at"]),
        }

    def reset_task(self, session_id: str) -> Dict[str, Any]:
        def fn(data: Dict[str, Any]) -> None:
            keep = {key: data.get(key) for key in ("session_id", "user_id", "created_at")}
            data.clear()
            data.update(keep)
            data.update(
                {
                    "state": "pose_category",
                    "pose_id": None,
                    "outfit_id": None,
                    "pose_batch": None,
                    "outfit_batch": None,
                    "seen": {"pose": {}, "outfit": {}},
                    "subject": None,
                    "spec": None,
                    "render": None,
                }
            )

        data = self.store.mutate(session_id, fn)
        return {"session_id": data["session_id"], "state": data["state"]}

    def go_back(self, session_id: str, target: str) -> Dict[str, Any]:
        def fn(data: Dict[str, Any]) -> None:
            current = data["state"]
            expected = BACK_TARGETS.get(current)
            if expected is None or target != expected:
                raise SkillError(
                    INVALID_STATE,
                    "不能从 %s 回退到 %s" % (current, target),
                    extra={"allowed_actions": list(ALLOWED_ACTIONS.get(current, []))},
                )
            if target == "pose_category":
                data.update({"pose_id": None, "pose_batch": None, "outfit_id": None, "outfit_batch": None,
                             "subject": None, "spec": None, "render": None})
            elif target == "pose_option":
                data.update({"outfit_id": None, "outfit_batch": None, "subject": None, "spec": None, "render": None})
            elif target == "outfit_category":
                data.update({"outfit_id": None, "outfit_batch": None, "subject": None, "spec": None, "render": None})
            elif target == "outfit_option":
                data.update({"subject": None, "spec": None, "render": None})
            elif target == "subject":
                data.update({"spec": None, "render": None})
            elif target == "spec_confirm":
                data.update({"render": None})
            data["state"] = target

        data = self.store.mutate(session_id, fn)
        return {"state": data["state"], "allowed_actions": list(ALLOWED_ACTIONS.get(data["state"], []))}

    # ------------------------------------------------------------------ 分类与候选
    def get_pose_categories(self, session_id: str) -> Dict[str, Any]:
        return self._categories(session_id, "pose")

    def get_outfit_categories(self, session_id: str) -> Dict[str, Any]:
        return self._categories(session_id, "outfit")

    def _categories(self, session_id: str, kind: str) -> Dict[str, Any]:
        data = self.store.read(session_id)
        if kind == "pose":
            require_state(data, "pose_category", "pose_option")
        else:
            require_state(data, "outfit_category", "outfit_option")
        self._license_gate(kind)
        return {"categories": self.library.categories(kind)}

    def sample_pose_options(self, session_id: str, category_id: str, reshuffle: bool = False) -> Dict[str, Any]:
        return self._sample(session_id, "pose", category_id, bool(reshuffle))

    def sample_outfit_options(self, session_id: str, category_id: str, reshuffle: bool = False) -> Dict[str, Any]:
        return self._sample(session_id, "outfit", category_id, bool(reshuffle))

    def _sample(self, session_id: str, kind: str, category_id: str, reshuffle: bool) -> Dict[str, Any]:
        result: Dict[str, Any] = {}

        def fn(data: Dict[str, Any]) -> None:
            if kind == "pose":
                require_state(data, "pose_category", "pose_option")
            else:
                require_state(data, "outfit_category", "outfit_option")
            self._license_gate(kind)
            if not self.library.category_allowed(kind, category_id):
                raise SkillError(CATEGORY_EMPTY, "该分类不存在")
            items = self.library.items(kind, category_id)
            if not items:
                raise SkillError(CATEGORY_EMPTY, "该分类暂无素材")
            batch_key = "pose_batch" if kind == "pose" else "outfit_batch"
            batch = data.get(batch_key)
            if not reshuffle and batch and batch.get("category_id") == category_id:
                result.update(self._batch_payload(data, kind, batch, len(items), notice=None))
                return

            seen_map = data["seen"][kind]
            seen = list(seen_map.get(category_id, []))
            seen_set = set(seen)
            pool = [item for item in items if item["id"] not in seen_set]
            restarted = False
            if not pool:
                if not reshuffle:
                    raise SkillError(
                        BATCH_EXHAUSTED,
                        "该分类 %d 项已全部展示" % len(items),
                        hint="说「换一批」可重新开始该分类",
                        extra={"total": len(items)},
                    )
                seen_map[category_id] = []
                seen = []
                pool = list(items)
                restarted = True

            picked = random.SystemRandom().sample(pool, min(self.config.session_max_batch, len(pool)))
            new_ids = [item["id"] for item in picked]
            seen.extend(new_ids)
            seen_map[category_id] = seen
            batch = {
                "batch_id": str(uuid.uuid4()),
                "kind": kind,
                "category_id": category_id,
                "item_ids": new_ids,
                "index_map": {str(index): item_id for index, item_id in enumerate(new_ids, 1)},
            }
            data[batch_key] = batch
            data["state"] = "pose_option" if kind == "pose" else "outfit_option"

            total = len(items)
            exhausted = len(seen) >= total
            if restarted:
                notice = "该分类已重新开始一轮"
            elif len(new_ids) < self.config.session_max_batch or exhausted:
                notice = "该分类共 %d 项，已全部展示" % total
            else:
                notice = None
            result.update(self._batch_payload(data, kind, batch, total, notice, exhausted))

        self.store.mutate(session_id, fn)
        return result

    def _batch_payload(
        self,
        data: Dict[str, Any],
        kind: str,
        batch: Dict[str, Any],
        total: int,
        notice: Optional[str],
        exhausted: bool = False,
    ) -> Dict[str, Any]:
        items: List[Dict[str, Any]] = []
        for index in range(1, len(batch["item_ids"]) + 1):
            item_id = batch["index_map"][str(index)]
            item = self.library.get(kind, item_id)
            if item is None:
                raise SkillError(INTERNAL_ERROR, "批次引用了不存在的素材: %s" % item_id)
            if kind == "pose":
                items.append(
                    {
                        "index": index,
                        "pose_id": item_id,
                        "label": item["label"],
                        "code": item.get("code", ""),
                        "subcategory": item.get("subcategory"),
                        "thumbnail": self.resolver.url("pose", item["thumbnail"]),
                    }
                )
            else:
                items.append(
                    {
                        "index": index,
                        "outfit_id": item_id,
                        "label": item["label"],
                        "thumbnail": self.resolver.url("outfit", item["thumbnail"]),
                    }
                )
        return {
            "batch_id": batch["batch_id"],
            "items": items,
            "total_in_category": total,
            "exhausted": bool(exhausted),
            "notice": notice,
        }

    def select_pose(self, session_id: str, ref: Any) -> Dict[str, Any]:
        return self._select(session_id, "pose", ref)

    def select_outfit(self, session_id: str, ref: Any) -> Dict[str, Any]:
        return self._select(session_id, "outfit", ref)

    def _select(self, session_id: str, kind: str, ref: Any) -> Dict[str, Any]:
        result: Dict[str, Any] = {}

        def fn(data: Dict[str, Any]) -> None:
            require_state(data, "pose_option" if kind == "pose" else "outfit_option")
            batch = data.get("pose_batch" if kind == "pose" else "outfit_batch")
            item_id = self._resolve_ref(batch, ref)
            if item_id is None:
                raise SkillError(
                    NOT_IN_BATCH,
                    "所选编号不在当前批次",
                    extra={"batch_size": len(batch["item_ids"]) if batch else 0},
                )
            item = self.library.get(kind, item_id)
            if item is None:
                raise SkillError(INVALID_ID, "素材不存在: %s" % item_id)
            if kind == "pose":
                data["pose_id"] = item_id
                data["state"] = "outfit_category"
                result.update({"pose_id": item_id, "label": item["label"], "state": data["state"]})
            else:
                data["outfit_id"] = item_id
                data["state"] = "subject"
                result.update({"outfit_id": item_id, "label": item["label"], "state": data["state"]})

        self.store.mutate(session_id, fn)
        return result

    @staticmethod
    def _resolve_ref(batch: Optional[Dict[str, Any]], ref: Any) -> Optional[str]:
        if not batch:
            return None
        if isinstance(ref, bool):
            return None
        if isinstance(ref, int):
            return batch["index_map"].get(str(ref))
        if isinstance(ref, str):
            value = ref.strip()
            if value.isdigit():
                return batch["index_map"].get(value)
            return ref if ref in batch["item_ids"] else None
        return None

    # ------------------------------------------------------------------ 主体与规格
    def receive_subject(
        self,
        session_id: str,
        image: Optional[Dict[str, Any]] = None,
        image_url: Optional[str] = None,
        description: Optional[str] = None,
        scope: Optional[str] = None,
        subject_style: Optional[str] = None,
    ) -> Dict[str, Any]:
        data = self.store.read(session_id)
        require_state(data, "subject")

        raw_description = description or ""
        if contains_adult(raw_description):
            raise SkillError(INVALID_INPUT, "主体描述包含不被允许的内容")
        clean_description = sanitize_subject_text(raw_description)
        if raw_description and not clean_description:
            raise SkillError(INVALID_INPUT, "主体描述清洗后为空")
        warnings: List[str] = []
        if len(raw_description) > 300:
            warnings.append("主体描述已截断到 300 字符")

        payload: Optional[bytes] = None
        mime: Optional[str] = None
        if image is not None:
            path = image.get("path") if isinstance(image, dict) else str(image)
            if not path:
                raise SkillError(INVALID_INPUT, "image.path 不能为空")
            payload, mime, stripped = read_subject_image(Path(path), self.config.subject_max_bytes)
            if not stripped:
                warnings.append("未安装 Pillow，未能剥离 EXIF")
        elif image_url:
            payload = fetch_public_image(image_url, self.config.asset_timeout, self.config.subject_max_bytes)
            mime = sniff_image(payload)
            payload, stripped = strip_exif(payload, mime)
            if not stripped:
                warnings.append("未安装 Pillow，未能剥离 EXIF")

        if payload is None and not clean_description:
            raise SkillError(INVALID_INPUT, "需要人像图片或文字描述，至少提供一项")

        image_file = self._save_subject(session_id, payload, mime) if payload is not None else None
        if image_file is None:
            subject_scope = "none"
        else:
            subject_scope = scope or "full"
            if subject_scope not in ("face", "upper", "full"):
                raise SkillError(INVALID_INPUT, "scope 只能是 face / upper / full")
        style_value = None
        if subject_style is not None:
            style_value = STYLE_ALIASES.get(str(subject_style).strip().lower(), str(subject_style).strip().lower())
            if style_value not in STYLE_BUNDLES:
                raise SkillError(INVALID_INPUT, "subject_style 只能是 anime / photo / 3d")

        def fn(cur: Dict[str, Any]) -> None:
            require_state(cur, "subject")
            cur["subject"] = {
                "image_file": image_file,
                "mime": mime,
                "description": clean_description or None,
                "scope": subject_scope,
                "style": style_value,
            }
            cur["state"] = "spec_confirm"

        self.store.mutate(session_id, fn)
        return {
            "subject_summary": self._subject_summary(
                {
                    "image_file": image_file,
                    "description": clean_description or None,
                    "scope": subject_scope,
                    "style": style_value,
                }
            ),
            "warnings": warnings,
        }

    def _save_subject(self, session_id: str, payload: bytes, mime: Optional[str]) -> str:
        directory = Path(self.config.state_dir) / "subjects" / session_id
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (uuid.uuid4().hex + EXT_BY_MIME.get(mime or "", ".img"))
        path.write_bytes(payload)
        return str(path)

    def set_spec(
        self,
        session_id: str,
        aspect_ratio: Optional[str] = None,
        size: Optional[str] = None,
        n: int = 1,
        seed: Optional[int] = None,
        style: Optional[str] = None,
        watermark: bool = False,
    ) -> Dict[str, Any]:
        data = self.store.read(session_id)
        subject_style = (data.get("subject") or {}).get("style")
        spec, validation = self._normalize_spec(aspect_ratio, size, n, seed, style or subject_style, watermark)

        def fn(data: Dict[str, Any]) -> None:
            require_state(data, "spec_confirm")
            data["spec"] = spec

        data = self.store.mutate(session_id, fn)
        caps = self.provider.capabilities()
        return {
            "spec": spec,
            "validation": validation,
            "risks": self._current_risks(data),
            "capabilities": {
                "supports_controlnet": bool(caps.get("supports_controlnet")),
                "supports_negative_prompt": bool(caps.get("supports_negative_prompt")),
                "max_reference_images": caps.get("max_reference_images"),
                "max_n": caps.get("max_n"),
            },
        }

    def _normalize_spec(
        self,
        aspect_ratio: Optional[str],
        size: Optional[str],
        n: int,
        seed: Optional[int],
        style: Optional[str],
        watermark: bool,
    ):
        aspect = aspect_ratio or DEFAULT_SPEC["aspect_ratio"]
        if aspect not in ASPECT_RATIOS:
            raise SkillError(INVALID_INPUT, "不支持的 aspect_ratio: %s" % aspect)
        caps = self.provider.capabilities()
        max_n = int(caps.get("max_n") or 1)
        if isinstance(n, bool) or not isinstance(n, int) or n < 1 or n > max_n:
            raise SkillError(INVALID_INPUT, "n 必须在 1..%d" % max_n)

        raw = str(size or SIZE_BY_ASPECT[aspect]).lower()
        match = re.fullmatch(r"(\d{3,4})x(\d{3,4})", raw)
        if not match:
            raise SkillError(INVALID_INPUT, "size 需要形如 1024x1536")
        width, height = int(match.group(1)), int(match.group(2))
        if not (512 <= width <= 2048 and 512 <= height <= 2048):
            raise SkillError(INVALID_INPUT, "单边必须在 512..2048 之间")
        if not (512 * 512 <= width * height <= 2048 * 2048):
            raise SkillError(INVALID_INPUT, "总像素必须在 512^2..2048^2 之间")
        ratio = width / height
        if ratio < 1 / 8 or ratio > 8:
            raise SkillError(INVALID_INPUT, "宽高比必须在 1:8..8:1 之间")
        warnings: List[str] = []
        if width % 8 or height % 8:
            width = max(512, min(2048, width // 8 * 8))
            height = max(512, min(2048, height // 8 * 8))
            warnings.append("尺寸已对齐到 8 的倍数: %dx%d" % (width, height))

        if seed is None:
            seed_value = random.SystemRandom().randint(0, 2**31 - 1)
        else:
            if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
                raise SkillError(INVALID_INPUT, "seed 必须是非负整数")
            seed_value = seed
        raw_style = (style or DEFAULT_SPEC["style"]).strip().lower()
        style_value = STYLE_ALIASES.get(raw_style, raw_style)
        if style_value not in STYLE_BUNDLES:
            raise SkillError(
                INVALID_INPUT,
                "不支持的 style: %s" % style,
                extra={"allowed": sorted(STYLE_BUNDLES)},
            )

        spec = {
            "aspect_ratio": aspect,
            "size": "%dx%d" % (width, height),
            "n": n,
            "seed": seed_value,
            "style": style_value,
            "watermark": bool(watermark),
        }
        return spec, {"normalized_size": spec["size"], "warnings": warnings}

    # ------------------------------------------------------------------ 渲染
    def confirm_and_render(self, session_id: str, confirmed: bool = False) -> Dict[str, Any]:
        if confirmed is not True:
            raise SkillError(INVALID_INPUT, "需要用户显式确认，confirmed 必须为 true")
        data = self.store.read(session_id)
        if data["state"] == "rendering":
            render = data.get("render") or {}
            return {"run_id": render.get("run_id"), "status": render.get("status", "RUNNING"),
                    "idempotency_key": render.get("idempotency_key")}
        if data["state"] == "completed":
            raise SkillError(
                ALREADY_COMPLETED,
                "任务已完成，未重复提交",
                extra={"render": self._render_summary(data.get("render")), "attribution": self._attribution(data)},
            )
        require_state(data, "spec_confirm")
        if not data.get("pose_id") or not data.get("outfit_id"):
            raise SkillError(INVALID_STATE, "缺少姿势或服装选择")

        spec, assets, idempotency_key = self._compose(data)
        submitted = self.provider.submit(spec, assets, idempotency_key)
        run_id = submitted.get("run_id")
        if not run_id:
            raise SkillError(INTERNAL_ERROR, "渲染器未返回 run_id")

        def fn(cur: Dict[str, Any]) -> None:
            if cur["state"] == "rendering":
                return
            require_state(cur, "spec_confirm")
            cur["render"] = {
                "run_id": run_id,
                "idempotency_key": idempotency_key,
                "status": "RUNNING",
                "spec": spec,
                "submitted_at": time.time(),
            }
            cur["state"] = "rendering"

        cur = self.store.mutate(session_id, fn)
        render = cur.get("render") or {}
        return {"run_id": render.get("run_id"), "status": render.get("status", "RUNNING"),
                "idempotency_key": idempotency_key}

    def _compose(self, data: Dict[str, Any]):
        pose = self.library.get("pose", data["pose_id"])
        outfit = self.library.get("outfit", data["outfit_id"])
        if pose is None or outfit is None:
            raise SkillError(INVALID_ID, "所选素材不存在")
        subject = data.get("subject") or {}
        has_image = bool(subject.get("image_file"))
        risks = self._risks(pose, outfit, data.get("spec") or {})
        style = normalize_style((data.get("spec") or {}).get("style"))
        include_outfit_image = True
        prompts = build_prompts(
            pose,
            outfit,
            subject.get("description"),
            has_image,
            style=style,
            include_outfit_image=include_outfit_image,
            risks=[risk["code"] for risk in risks],
            subject_scope=(subject.get("scope") or ("full" if has_image else "none")),
        )

        assets: Dict[str, Any] = {
            "pose": {
                "id": pose["id"],
                "label": pose["label"],
                "control_type": pose.get("control_type", "lineart"),
                "ref_url": resolve_asset_url("pose", pose["ref_image"]),
                "thumbnail_url": resolve_asset_url("pose", pose["thumbnail"]),
                "source_url": pose["source_url"],
                "author": pose["author"],
                "license": pose["license"],
            },
            "outfit": {
                "id": outfit["id"],
                "label": outfit["label"],
                "ref_url": resolve_asset_url("outfit", outfit["ref_image"]) if include_outfit_image else None,
                "omitted": not include_outfit_image,
                "thumbnail_url": resolve_asset_url("outfit", outfit["thumbnail"]),
                "source_url": outfit["source_url"],
                "author": outfit["author"],
                "license": outfit["license"],
            },
            "subject": None,
            "reference_order": prompts["reference_order"],
        }
        if has_image:
            assets["subject"] = {
                "kind": "image+description" if subject.get("description") else "image",
                "file": subject["image_file"],
                "mime": subject.get("mime"),
                "description": subject.get("description"),
            }
        elif subject.get("description"):
            assets["subject"] = {"kind": "description", "description": subject["description"]}

        spec = dict(data.get("spec") or DEFAULT_SPEC)
        spec["prompt"] = prompts
        payload = json.dumps(spec, sort_keys=True, ensure_ascii=False)
        idempotency_key = hashlib.sha256(
            ("%s|%s|%s" % (data["session_id"], data.get("version", 0), payload)).encode("utf-8")
        ).hexdigest()[:32]
        return spec, assets, idempotency_key

    def get_render_status(self, session_id: str) -> Dict[str, Any]:
        data = self.store.read(session_id)
        render = data.get("render")
        if not render:
            raise SkillError(INVALID_STATE, "当前会话没有渲染任务")
        result = self.provider.poll(render["run_id"])
        status = result.get("status")
        if status == "COMPLETED":
            def fn(cur: Dict[str, Any]) -> None:
                current = cur.get("render") or {}
                if current.get("run_id") != render["run_id"]:
                    return
                current["status"] = "COMPLETED"
                current["images"] = result.get("images") or []
                cur["render"] = current
                cur["state"] = "completed"

            data = self.store.mutate(session_id, fn)
        elif status == "FAILED":
            def fn(cur: Dict[str, Any]) -> None:
                current = cur.get("render") or {}
                if current.get("run_id") != render["run_id"]:
                    return
                current["status"] = "FAILED"
                current["error"] = result.get("error") or {"code": "RENDER_FAILED", "message": "渲染失败"}
                cur["render"] = current
                cur["state"] = "failed"

            data = self.store.mutate(session_id, fn)

        current = data.get("render") or {}
        outfit = self.library.get("outfit", data.get("outfit_id")) if data.get("outfit_id") else None
        checklist = []
        if outfit:
            checklist = [token for token, _ in accessory_tokens(str(outfit.get("keywords", "")))]
        return {
            "run_id": current.get("run_id"),
            "status": current.get("status"),
            "images": current.get("images") or [],
            "error": current.get("error"),
            "checklist": {"accessories": checklist, "note": "请核对配件是否齐全（如帽子、包、眼镜）"},
            "attribution": self._attribution(data),
        }

    # ------------------------------------------------------------------ 辅助
    def _risks(self, pose: Optional[dict], outfit: Optional[dict], spec: Dict[str, Any]) -> List[Dict[str, str]]:
        risks: List[Dict[str, str]] = []
        if pose and outfit:
            text = "%s %s" % (pose.get("label", ""), pose.get("subcategory", ""))
            feet_exposed = pose.get("subcategory") in {"趴卧"} or any(
                token in text for token in ("脚", "腿", "翘", "抬", "卧", "趴")
            )
            has_shoes = any(
                token in str(outfit.get("keywords", "")).lower()
                for token in ("shoe", "sneaker", "boot", "sandal", "heel", "slipper")
            )
            if feet_exposed and has_shoes:
                risks.append(
                    {
                        "code": "FOOTWEAR_ORIENTATION",
                        "severity": "medium",
                        "message": "该姿势脚部朝后或可能露出鞋底，鞋面与鞋底容易混淆",
                        "hint": "确认时提醒用户；必要时换不含鞋的服装，或改用支持 ControlNet 的渲染器",
                    }
                )
        style = normalize_style(spec.get("style"))
        if pose and outfit and style != "photo":
            risks.append(
                {
                    "code": "STYLE_TRANSFER",
                    "severity": "info",
                    "message": "服装参考图是写实照片，已要求按主体风格重绘，仍可能残留写实质感",
                    "hint": "若服装被拉向写实，可改用风格化的服装参考图，或降低服装图权重",
                }
            )
        return risks

    def _current_risks(self, data: Dict[str, Any]) -> List[Dict[str, str]]:
        pose = self.library.get("pose", data.get("pose_id")) if data.get("pose_id") else None
        outfit = self.library.get("outfit", data.get("outfit_id")) if data.get("outfit_id") else None
        return self._risks(pose, outfit, data.get("spec") or {})

    def _license_gate(self, kind: str) -> None:
        if kind == "pose" and self.config.commercial and self.config.pose_library == "upstream":
            raise SkillError(
                LICENSE_BLOCKED,
                "当前为商用部署，姿势库授权不允许商用",
                extra={"pose_library": self.config.pose_library, "deployment": self.config.deployment},
            )

    def _batch_summary(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        summary: Dict[str, Any] = {}
        for kind, key in (("pose", "pose_batch"), ("outfit", "outfit_batch")):
            batch = data.get(key)
            if batch:
                summary[kind] = {
                    "batch_id": batch["batch_id"],
                    "category_id": batch["category_id"],
                    "item_ids": list(batch["item_ids"]),
                }
        return summary or None

    @staticmethod
    def _subject_summary(subject: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not subject:
            return None
        return {
            "has_image": bool(subject.get("image_file")),
            "scope": subject.get("scope") or ("full" if subject.get("image_file") else "none"),
            "style": subject.get("style"),
            "description": subject.get("description") or "",
        }

    @staticmethod
    def _render_summary(render: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not render:
            return None
        return {
            "run_id": render.get("run_id"),
            "status": render.get("status"),
            "images": render.get("images") or [],
            "error": render.get("error"),
        }

    def _attribution(self, data: Dict[str, Any]) -> Dict[str, Any]:
        def brief(kind: str, item_id: Optional[str]) -> Optional[Dict[str, Any]]:
            item = self.library.get(kind, item_id) if item_id else None
            if item is None:
                return None
            return {
                "id": item["id"],
                "label": item["label"],
                "source": item["source"],
                "source_url": item["source_url"],
                "author": item["author"],
                "license": item["license"],
            }

        return {
            "pose": brief("pose", data.get("pose_id")),
            "outfit": brief("outfit", data.get("outfit_id")),
        }
