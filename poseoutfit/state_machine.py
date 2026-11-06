from __future__ import annotations

from typing import Dict, List

STATES = (
    "pose_category",
    "pose_option",
    "outfit_category",
    "outfit_option",
    "subject",
    "spec_confirm",
    "rendering",
    "completed",
    "failed",
)

ALLOWED_ACTIONS: Dict[str, List[str]] = {
    "pose_category": ["get_pose_categories", "sample_pose_options", "reset_task"],
    "pose_option": ["sample_pose_options", "select_pose", "go_back", "reset_task"],
    "outfit_category": ["get_outfit_categories", "sample_outfit_options", "go_back", "reset_task"],
    "outfit_option": ["sample_outfit_options", "select_outfit", "go_back", "reset_task"],
    "subject": ["receive_subject", "go_back", "reset_task"],
    "spec_confirm": ["set_spec", "confirm_and_render", "go_back", "reset_task"],
    "rendering": ["get_render_status", "reset_task"],
    "completed": ["get_render_status", "go_back", "reset_task"],
    "failed": ["get_render_status", "go_back", "reset_task"],
}

BACK_TARGETS: Dict[str, str] = {
    "pose_option": "pose_category",
    "outfit_category": "pose_option",
    "outfit_option": "outfit_category",
    "subject": "outfit_option",
    "spec_confirm": "subject",
    "failed": "spec_confirm",
    "completed": "spec_confirm",
}
