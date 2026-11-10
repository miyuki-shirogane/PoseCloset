from __future__ import annotations

from typing import Any, Dict, List

SESSION = {"type": "string", "description": "start_pose_task 返回的会话 id"}


def _schema(properties: Dict[str, Any], required: List[str] = ()) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


TOOL_SPECS = [
    {
        "name": "start_pose_task",
        "description": (
            "新建一个 pose+outfit 生图会话。用户表达「想拍照/生成一张/换装出图」等意图且当前没有会话时调用。"
            "返回 session_id，后续所有工具都要带上它。"
        ),
        "inputSchema": _schema({"user_id": {"type": "string", "description": "可选，调用方用户标识"}}),
    },
    {
        "name": "get_session_state",
        "description": (
            "读取会话当前状态与已选项、可用动作。会话中断、上下文丢失、或不确定下一步该调用什么时先调用它。"
        ),
        "inputSchema": _schema({"session_id": SESSION}, ["session_id"]),
    },
    {
        "name": "get_pose_categories",
        "description": (
            "返回当前可用的姿势分类、每类素材数量与子类数量。分类/子类只能来自本工具的返回，禁止自行编造。"
            "广告/成人向分类不会出现，也不要用其它词替代。"
        ),
        "inputSchema": _schema({"session_id": SESSION}, ["session_id"]),
    },
    {
        "name": "sample_pose_options",
        "description": (
            "在指定姿势分类内随机取候选，默认 5 个（可用 limit 指定，最多 20）；可按 subcategory 过滤。"
            "用户说「换一批」时传 reshuffle=true。编号只在本次批次内有效；旧批次的项可用 id 选择。"
        ),
        "inputSchema": _schema(
            {
                "session_id": SESSION,
                "category_id": {"type": "string", "description": "get_pose_categories 返回的分类 id"},
                "reshuffle": {"type": "boolean", "default": False, "description": "true 表示换一批"},
                "subcategory": {
                    "type": "string",
                    "description": "可选，姿势子类（如 站姿/坐姿/趴卧）；先用 get_pose_categories 查看可用子类",
                },
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 5,
                    "description": "本批数量，默认 5，最多 20",
                },
            },
            ["session_id", "category_id"],
        ),
    },
    {
        "name": "select_pose",
        "description": (
            "锁定一个姿势。ref 可以是当前批编号（1..N）、当前批的 pose_id，或本会话已展示过的 pose_id；"
            "未展示过的 id 返回 NOT_IN_BATCH，禁止全局检索。"
        ),
        "inputSchema": _schema(
            {
                "session_id": SESSION,
                "ref": {"type": ["integer", "string"], "description": "本批编号、当前批 pose_id，或本会话已展示过的 pose_id"},
            },
            ["session_id", "ref"],
        ),
    },
    {
        "name": "get_outfit_categories",
        "description": "返回当前可用的服装分类及数量，分类只能来自本工具返回。",
        "inputSchema": _schema({"session_id": SESSION}, ["session_id"]),
    },
    {
        "name": "sample_outfit_options",
        "description": (
            "在指定服装分类内随机取候选，默认 5 个（可用 limit 指定，最多 20）。"
            "用户说「换一批」时传 reshuffle=true。编号只在本次批次内有效；旧批次的项可用 id 选择。"
        ),
        "inputSchema": _schema(
            {
                "session_id": SESSION,
                "category_id": {"type": "string"},
                "reshuffle": {"type": "boolean", "default": False},
                "limit": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 5,
                    "description": "本批数量，默认 5，最多 20",
                },
            },
            ["session_id", "category_id"],
        ),
    },
    {
        "name": "select_outfit",
        "description": "锁定一套服装。ref 可以是当前批编号、当前批的 outfit_id，或本会话已展示过的 outfit_id。",
        "inputSchema": _schema(
            {
                "session_id": SESSION,
                "ref": {"type": ["integer", "string"]},
            },
            ["session_id", "ref"],
        ),
    },
    {
        "name": "receive_subject",
        "description": (
            "接收出图主体：本地人像图片路径、公网图片 URL、或文字描述，至少提供一项。"
            "只有主体描述允许自由文本，且会被清洗与长度截断；不要用它夹带姿势/服装要求。"
        ),
        "inputSchema": _schema(
            {
                "session_id": SESSION,
                "image": _schema({"path": {"type": "string", "description": "本地图片绝对路径"}}, ["path"]),
                "image_url": {"type": "string", "description": "公网 https 图片地址"},
                "description": {"type": "string", "description": "人物特征描述，最多 300 字"},
                "scope": {
                    "type": "string",
                    "enum": ["face", "upper", "full"],
                    "description": "主体图范围：face 仅脸、upper 半身、full 全身。含身体时比例取自主体图；仅脸时比例取自姿势图。默认 full",
                },
                "subject_style": {
                    "type": "string",
                    "enum": ["anime", "photo", "3d"],
                    "description": "主体图的画风。输出画风以主体为准；不传时 set_spec 需显式指定 style",
                },
            },
            ["session_id"],
        ),
    },
    {
        "name": "set_spec",
        "description": (
            "设置输出规格（比例、尺寸、张数、随机种子、风格）。style 不传时使用主体图登记的画风。不传 size 时按比例给默认尺寸。"
            "返回 risks 时必须原样告知用户。生成前必须让用户确认最终方案。"
        ),
        "inputSchema": _schema(
            {
                "session_id": SESSION,
                "aspect_ratio": {"type": "string", "enum": ["1:1", "3:4", "4:3", "2:3", "3:2", "9:16", "16:9"]},
                "size": {"type": "string", "description": "宽x高，如 1024x1536；512-2048，可被 8 整除"},
                "n": {"type": "integer", "minimum": 1, "default": 1},
                "seed": {"type": "integer", "minimum": 0},
                "style": {
                    "type": "string",
                    "enum": ["anime", "photo", "3d"],
                    "description": "画风：anime 动漫、photo 写实、3d 三维。默认 photo；动漫主体务必选 anime",
                },
                "watermark": {"type": "boolean", "default": False},
            },
            ["session_id"],
        ),
    },
    {
        "name": "confirm_and_render",
        "description": (
            "用户明确确认最终方案后提交渲染。未确认时不要调用。返回 run_id 后需轮询 get_render_status。"
            "同一会话重复调用是幂等的，不会重复出图。"
        ),
        "inputSchema": _schema(
            {
                "session_id": SESSION,
                "confirmed": {"type": "boolean", "const": True, "description": "必须为 true，表示用户已确认方案"},
            },
            ["session_id", "confirmed"],
        ),
    },
    {
        "name": "get_render_status",
        "description": "查询渲染进度与结果。RUNNING 时告知用户仍在生成，不要重复提交；COMPLETED 时返回图片与署名。",
        "inputSchema": _schema({"session_id": SESSION}, ["session_id"]),
    },
    {
        "name": "go_back",
        "description": (
            "回退一步：pose_option→pose_category、outfit_category→pose_option、"
            "outfit_option→outfit_category、subject→outfit_option。回退会清空下游选择。"
        ),
        "inputSchema": _schema(
            {"session_id": SESSION, "target": {"type": "string", "description": "目标状态"}},
            ["session_id", "target"],
        ),
    },
    {
        "name": "reset_task",
        "description": "用户说「重来」时清空当前任务并回到选择姿势分类，保留 session_id。",
        "inputSchema": _schema({"session_id": SESSION}, ["session_id"]),
    },
]

TOOL_NAMES = {spec["name"] for spec in TOOL_SPECS}
