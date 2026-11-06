from __future__ import annotations

import time
import unittest
from pathlib import Path

from poseoutfit.render.mock import MockProvider
from poseoutfit.tools import Skill

from .support import SkillTestCase
from .test_render import PNG_1PX


class FlowTests(SkillTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.provider = MockProvider(self.config, delay_seconds=0.05)
        self.skill = Skill(self.config, provider=self.provider)
        self.sid = self.ok("start_pose_task")["session_id"]

    def test_full_chain_ten_steps(self) -> None:
        self.assertEqual(self.ok("get_session_state", session_id=self.sid)["state"], "pose_category")
        categories = self.ok("get_pose_categories", session_id=self.sid)["categories"]
        self.assertTrue(categories)
        batch = self.ok("sample_pose_options", session_id=self.sid, category_id=categories[0]["id"])
        self.assertLessEqual(len(batch["items"]), 5)
        picked_pose = self.ok("select_pose", session_id=self.sid, ref=batch["items"][0]["index"])
        self.assertEqual(picked_pose["state"], "outfit_category")
        outfit_categories = self.ok("get_outfit_categories", session_id=self.sid)["categories"]
        outfit_batch = self.ok(
            "sample_outfit_options", session_id=self.sid, category_id=outfit_categories[0]["id"]
        )
        picked_outfit = self.ok("select_outfit", session_id=self.sid, ref=outfit_batch["items"][0]["index"])
        self.assertEqual(picked_outfit["state"], "subject")
        subject = self.ok("receive_subject", session_id=self.sid, description="短黑发，米色风衣，自然妆")
        self.assertFalse(subject["subject_summary"]["has_image"])
        spec = self.ok("set_spec", session_id=self.sid, aspect_ratio="3:4", seed=7)
        self.assertEqual(spec["spec"]["aspect_ratio"], "3:4")
        run = self.ok("confirm_and_render", session_id=self.sid, confirmed=True)
        self.assertTrue(run["run_id"])
        time.sleep(0.1)
        status = self.ok("get_render_status", session_id=self.sid)
        self.assertEqual(status["status"], "COMPLETED")
        self.assertEqual(len(status["images"]), 1)
        self.assertEqual(self.ok("get_session_state", session_id=self.sid)["state"], "completed")

    def test_reshuffle_changes_candidates(self) -> None:
        first = self.ok("sample_pose_options", session_id=self.sid, category_id="full")
        second = self.ok("sample_pose_options", session_id=self.sid, category_id="full", reshuffle=True)
        self.assertNotEqual(
            {item["pose_id"] for item in first["items"]},
            {item["pose_id"] for item in second["items"]},
        )

    def test_go_back_chain_clears_downstream(self) -> None:
        self.pick_pose("full")
        self.ok("go_back", session_id=self.sid, target="pose_option")
        self.ok("go_back", session_id=self.sid, target="pose_category")
        state = self.ok("get_session_state", session_id=self.sid)
        self.assertEqual(state["state"], "pose_category")
        self.assertIsNone(state["selections"]["pose_id"])

        self.ok("sample_pose_options", session_id=self.sid, category_id="bust")
        self.ok("select_pose", session_id=self.sid, ref=1)
        self.ok("sample_outfit_options", session_id=self.sid, category_id="春")
        self.ok("select_outfit", session_id=self.sid, ref=1)
        self.assertEqual(self.ok("get_session_state", session_id=self.sid)["state"], "subject")
        self.ok("go_back", session_id=self.sid, target="outfit_option")
        state = self.ok("get_session_state", session_id=self.sid)
        self.assertEqual(state["state"], "outfit_option")
        self.assertIsNone(state["subject"])
        self.assertEqual(state["selections"]["pose_id"][:4], "bust")

    def test_reset_allows_new_task(self) -> None:
        self.pick_pose("full")
        self.pick_outfit("春")
        self.ok("receive_subject", session_id=self.sid, description="短黑发")
        self.ok("set_spec", session_id=self.sid)
        self.ok("confirm_and_render", session_id=self.sid, confirmed=True)
        time.sleep(0.1)
        self.ok("get_render_status", session_id=self.sid)
        self.assertEqual(self.ok("get_session_state", session_id=self.sid)["state"], "completed")
        self.ok("reset_task", session_id=self.sid)
        again = self.ok("sample_pose_options", session_id=self.sid, category_id="full")
        self.assertTrue(again["items"])

    def test_image_subject_is_persisted(self) -> None:
        image_path = self.tmp / "subject.png"
        image_path.write_bytes(PNG_1PX)
        self.pick_pose("full")
        self.pick_outfit("春")
        data = self.ok("receive_subject", session_id=self.sid, image={"path": str(image_path)})
        self.assertTrue(data["subject_summary"]["has_image"])
        stored = list((Path(self.config.state_dir) / "subjects" / self.sid).glob("*"))
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].read_bytes(), PNG_1PX)

    def test_ten_sequential_sessions(self) -> None:
        for _ in range(10):
            session_id = self.ok("start_pose_task")["session_id"]
            self.ok("sample_pose_options", session_id=session_id, category_id="full")
            self.ok("select_pose", session_id=session_id, ref=1)
            self.ok("sample_outfit_options", session_id=session_id, category_id="春")
            self.ok("select_outfit", session_id=session_id, ref=1)
            self.ok("receive_subject", session_id=session_id, description="短黑发")
            self.ok("set_spec", session_id=session_id)
            self.ok("confirm_and_render", session_id=session_id, confirmed=True)
            time.sleep(0.1)
            self.assertEqual(self.ok("get_render_status", session_id=session_id)["status"], "COMPLETED")


if __name__ == "__main__":
    unittest.main()
