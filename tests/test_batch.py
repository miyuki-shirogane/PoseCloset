from __future__ import annotations

import unittest

from .support import SkillTestCase


class BatchTests(SkillTestCase):
    def test_default_batch_is_five(self) -> None:
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

    def test_batch_size_config_caps_at_twenty(self) -> None:
        from poseoutfit.config import Config

        config = Config(
            index_path=self.config.index_path,
            state_dir=self.tmp / "state2",
            renderer="mock",
            session_max_batch=99,
        )
        self.assertEqual(config.session_max_batch, 20)

    def test_custom_limit(self) -> None:
        sid = self.ok("start_pose_task")["session_id"]
        small = self.ok("sample_pose_options", session_id=sid, category_id="full", limit=3)
        self.assertEqual(len(small["items"]), 3)
        sid2 = self.ok("start_pose_task")["session_id"]
        large = self.ok("sample_pose_options", session_id=sid2, category_id="full", limit=10)
        self.assertEqual(len(large["items"]), 7)
        self.assertEqual(large["total_in_scope"], 7)
        self.assertIn("共 7 项", large["notice"] or "")

    def test_limit_validation(self) -> None:
        self.assertEqual(self.error("sample_pose_options", session_id=self.sid, category_id="full", limit=0), "INVALID_INPUT")
        self.assertEqual(self.error("sample_pose_options", session_id=self.sid, category_id="full", limit=21), "INVALID_INPUT")

    def test_subcategory_filter(self) -> None:
        sid = self.ok("start_pose_task")["session_id"]
        data = self.ok("sample_pose_options", session_id=sid, category_id="full", subcategory="站姿")
        self.assertEqual(len(data["items"]), 5)
        self.assertTrue(all(item["subcategory"] == "站姿" for item in data["items"]))
        self.assertEqual(data["total_in_scope"], 7)
        self.assertEqual(
            self.error("sample_pose_options", session_id=sid, category_id="full", subcategory="坐姿"),
            "CATEGORY_EMPTY",
        )

    def test_subcategories_listed(self) -> None:
        categories = self.ok("get_pose_categories", session_id=self.sid)["categories"]
        full = next(item for item in categories if item["id"] == "full")
        self.assertIn({"name": "站姿", "count": 7}, full["subcategories"])

    def test_select_previous_batch_item(self) -> None:
        sid = self.ok("start_pose_task")["session_id"]
        first = self.ok("sample_pose_options", session_id=sid, category_id="full")
        first_id = first["items"][0]["pose_id"]
        self.ok("sample_pose_options", session_id=sid, category_id="full", reshuffle=True)
        selected = self.ok("select_pose", session_id=sid, ref=first_id)
        self.assertEqual(selected["pose_id"], first_id)
        self.assertEqual(selected["state"], "outfit_category")

    def test_outfit_batch(self) -> None:
        self.pick_pose("full")
        data = self.ok("sample_outfit_options", session_id=self.sid, category_id="春")
        self.assertEqual(len(data["items"]), 5)
        self.assertEqual(data["total_in_category"], 6)


if __name__ == "__main__":
    unittest.main()
