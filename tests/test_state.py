from __future__ import annotations

import unittest

from .support import SkillTestCase


class StateGuardTests(SkillTestCase):
    def test_select_pose_requires_pose_option(self) -> None:
        self.assertEqual(self.error("select_pose", session_id=self.sid, ref=1), "INVALID_STATE")

    def test_select_outfit_in_wrong_state(self) -> None:
        self.pick_pose("full")
        self.assertEqual(self.error("select_outfit", session_id=self.sid, ref=1), "INVALID_STATE")

    def test_confirm_requires_explicit_flag(self) -> None:
        self.pick_pose("full")
        self.pick_outfit("春")
        self.ok("receive_subject", session_id=self.sid, description="短黑发")
        self.ok("set_spec", session_id=self.sid)
        self.assertEqual(self.error("confirm_and_render", session_id=self.sid, confirmed=False), "INVALID_INPUT")

    def test_confirm_in_wrong_state(self) -> None:
        self.assertEqual(
            self.error("confirm_and_render", session_id=self.sid, confirmed=True), "INVALID_STATE"
        )

    def test_go_back_only_one_step(self) -> None:
        self.pick_pose("full")
        self.assertEqual(self.error("go_back", session_id=self.sid, target="pose_category"), "INVALID_STATE")
        self.assertEqual(self.ok("go_back", session_id=self.sid, target="pose_option")["state"], "pose_option")
        self.assertEqual(self.ok("go_back", session_id=self.sid, target="pose_category")["state"], "pose_category")

    def test_go_back_from_spec_confirm(self) -> None:
        self.pick_pose("full")
        self.pick_outfit("春")
        self.ok("receive_subject", session_id=self.sid, description="短黑发")
        self.ok("set_spec", session_id=self.sid)
        state = self.ok("go_back", session_id=self.sid, target="subject")
        self.assertEqual(state["state"], "subject")
        current = self.ok("get_session_state", session_id=self.sid)
        self.assertIsNone(current["spec"])
        self.assertTrue(current["subject"]["has_image"] is False)

    def test_regenerate_from_completed_keeps_selection(self) -> None:
        self.pick_pose("full")
        self.pick_outfit("春")
        self.ok("receive_subject", session_id=self.sid, description="短黑发")
        self.ok("set_spec", session_id=self.sid)
        self.ok("confirm_and_render", session_id=self.sid, confirmed=True)
        import time

        time.sleep(1.1)
        self.ok("get_render_status", session_id=self.sid)
        self.assertEqual(self.ok("get_session_state", session_id=self.sid)["state"], "completed")
        self.ok("go_back", session_id=self.sid, target="spec_confirm")
        state = self.ok("get_session_state", session_id=self.sid)
        self.assertEqual(state["state"], "spec_confirm")
        self.assertIsNotNone(state["selections"]["pose_id"])
        self.assertIsNone(state["render"])

    def test_reset_keeps_session(self) -> None:
        self.pick_pose("full")
        data = self.ok("reset_task", session_id=self.sid)
        self.assertEqual(data["session_id"], self.sid)
        state = self.ok("get_session_state", session_id=self.sid)
        self.assertEqual(state["state"], "pose_category")
        self.assertIsNone(state["selections"]["pose_id"])

    def test_unknown_session(self) -> None:
        self.assertEqual(self.error("get_session_state", session_id="missing"), "SESSION_NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
