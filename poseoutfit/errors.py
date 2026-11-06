from __future__ import annotations

from typing import Any, Dict, Optional

INVALID_STATE = "INVALID_STATE"
INVALID_ID = "INVALID_ID"
NOT_IN_BATCH = "NOT_IN_BATCH"
CATEGORY_EMPTY = "CATEGORY_EMPTY"
BATCH_EXHAUSTED = "BATCH_EXHAUSTED"
INVALID_INPUT = "INVALID_INPUT"
SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
LIBRARY_UNAVAILABLE = "LIBRARY_UNAVAILABLE"
ASSET_UNREACHABLE = "ASSET_UNREACHABLE"
ASSET_PATH_BLOCKED = "ASSET_PATH_BLOCKED"
LICENSE_BLOCKED = "LICENSE_BLOCKED"
RENDER_FAILED = "RENDER_FAILED"
RENDER_TIMEOUT = "RENDER_TIMEOUT"
ALREADY_COMPLETED = "ALREADY_COMPLETED"
INTERNAL_ERROR = "INTERNAL_ERROR"

HINTS = {
    INVALID_STATE: "调用 get_session_state 查看 allowed_actions 后重试",
    INVALID_ID: "只能使用索引中存在的 id",
    NOT_IN_BATCH: "调用 sample_pose_options / sample_outfit_options 重新取批",
    CATEGORY_EMPTY: "该分类不可用，回到当前步骤重新选择",
    BATCH_EXHAUSTED: "该分类已全部展示，可切换分类或重来",
    INVALID_INPUT: "按提示修正输入后重试",
    SESSION_NOT_FOUND: "调用 start_pose_task 新建会话",
    LIBRARY_UNAVAILABLE: "检查 index/pose_outfit_index.json 是否完整且通过校验",
    ASSET_UNREACHABLE: "素材站暂时读不到，稍后重试或换一个候选",
    ASSET_PATH_BLOCKED: "索引中的素材路径非法，拒绝访问",
    LICENSE_BLOCKED: "当前部署模式不允许使用该素材库，请替换为自有或已授权素材",
    RENDER_FAILED: "读取 error 后决定是否重试，禁止自动重复提交",
    RENDER_TIMEOUT: "调用 get_render_status 继续查询原 run_id",
    ALREADY_COMPLETED: "任务已完成，直接使用返回的图片；如需新图请先 reset_task",
    INTERNAL_ERROR: "内部错误，请检查输入后重试",
}


class SkillError(Exception):
    def __init__(
        self,
        code: str,
        message: Optional[str] = None,
        hint: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message or code)
        self.code = code
        self.message = message or code
        self.hint = hint if hint is not None else HINTS.get(code)
        self.extra = extra or {}

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"code": self.code, "message": self.message}
        if self.hint:
            payload["hint"] = self.hint
        if self.extra:
            payload["details"] = self.extra
        return payload


def ok(data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"ok": True, "data": data or {}}


def fail(error: SkillError) -> Dict[str, Any]:
    return {"ok": False, "error": error.to_dict()}
