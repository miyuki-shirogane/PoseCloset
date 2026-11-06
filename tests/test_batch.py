from __future__ import annotations

import unittest

from .support import SkillTestCase


class BatchTests(SkillTestCase):
    def test_batch_is_capped_at_five(self) -> None:
        data = self.ok("sample_pose_options", session_id=self.sid, category_id="full")
        self.assertEqual(len(data["items"]), 5)
        self.assertEqual(data["total_in_category"], 7)
        self.assertFalse(data["exhausted"])

    def test_reshuffle_excludes_shown_and_exhausts(self) -> None:
        first = self.ok("sample_pose_options", session_id=self.sid, category_id="full")
        second = self.ok("sample_pose_options", session_id=self.sid, category_id="full", reshuffle=True)
        self.assertEqual(len(second["items"]), 2)
        self.assertIn("共 7 项", second["notice"] or "")
        first_ids = {item["pose_id"] for item in first["items"]}
        second_ids = {item["pose_id"] for item in second["items"]}
        self.assertFalse(first_ids & second_ids)
        restarted = self.ok("sample_pose_options", session_id=self.sid, category_id="full", reshuffle=True)
        self.assertEqual(len(restarted["items"]), 5)
        self.assertIn("重新开始", restarted["notice"] or "")

    def test_exhausted_without_reshuffle_returns_error(self) -> None:
        self.ok("sample_pose_options", session_id=self.sid, category_id="full")
        self.ok("sample_pose_options", session_id=self.sid, category_id="full", reshuffle=True)
        self.ok("sample_pose_options", session_id=self.sid, category_id="bust")
        self.assertEqual(self.error("sample_pose_options", session_id=self.sid, category_id="full"), "BATCH_EXHAUSTED")

    def test_small_category_returns_all(self) -> None:
        data = self.ok("sample_pose_options", session_id=self.sid, category_id="bust")
        self.assertEqual(len(data["items"]), 2)
        self.assertIn("共 2 项", data["notice"] or "")

    def test_reshuffle_stays_in_category(self) -> None:
        self.ok("sample_pose_options", session_id=self.sid, category_id="full")
        data = self.ok("sample_pose_options", session_id=self.sid, category_id="full", reshuffle=True)
        ids = {item["pose_id"] for item in data["items"]}
        allowed = {item["id"] for item in self.index["poses"] if item["category"]["id"] == "full"}
        self.assertTrue(ids <= allowed)

    def test_select_index_out_of_range(self) -> None:
        self.ok("sample_pose_options", session_id=self.sid, category_id="full")
        self.assertEqual(self.error("select_pose", session_id=self.sid, ref=99), "NOT_IN_BATCH")

    def test_select_id_outside_batch(self) -> None:
        self.ok("sample_pose_options", session_id=self.sid, category_id="full")
        outside = [item["id"] for item in self.index["poses"] if item["category"]["id"] == "bust"][0]
        self.assertEqual(self.error("select_pose", session_id=self.sid, ref=outside), "NOT_IN_BATCH")

    def test_reshuffle_false_is_idempotent(self) -> None:
        first = self.ok("sample_pose_options", session_id=self.sid, category_id="full")
        second = self.ok("sample_pose_options", session_id=self.sid, category_id="full")
        self.assertEqual(first["batch_id"], second["batch_id"])
        self.assertEqual([i["pose_id"] for i in first["items"]], [i["pose_id"] for i in second["items"]])

    def test_batch_size_cannot_exceed_five(self) -> None:
        from poseoutfit.config import Config
        from poseoutfit.tools import Skill

        config = Config(
            index_path=self.config.index_path,
            state_dir=self.tmp / "state2",
            renderer="mock",
            session_max_batch=9,
        )
        skill = Skill(config)
        sid = skill.call("start_pose_task", {})["data"]["session_id"]
        data = skill.call("sample_pose_options", {"session_id": sid, "category_id": "full"})["data"]
        self.assertEqual(len(data["items"]), 5)

    def test_outfit_batch(self) -> None:
        self.pick_pose("full")
        data = self.ok("sample_outfit_options", session_id=self.sid, category_id="春")
        self.assertEqual(len(data["items"]), 5)
        self.assertEqual(data["total_in_category"], 6)


if __name__ == "__main__":
    unittest.main()
