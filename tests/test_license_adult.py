from __future__ import annotations

import json
import unittest
from pathlib import Path

from poseoutfit.config import Config
from poseoutfit.errors import LIBRARY_UNAVAILABLE, SkillError
from poseoutfit.library import Library
from poseoutfit.tools import Skill

from .support import SkillTestCase


class SourceExclusionTests(SkillTestCase):
    def test_build_drops_everything_outside_allowlist(self) -> None:
        self.assertEqual(len(self.index["poses"]), 9)
        self.assertEqual(len(self.index["outfits"]), 6)
        ids = {item["id"] for item in self.index["poses"]}
        self.assertIn("full_single_P001", ids)
        self.assertIn("bust_single_P001", ids)
        self.assertNotIn("sexy_single_P001", ids)
        self.assertNotIn("pair_single_P001", ids)
        self.assertNotIn("bust_single_P099", ids)
        self.assertEqual(self.meta["excluded"]["pose_outside_allowlist"], 5)
        self.assertEqual(self.meta["excluded"]["pose_adult"], 1)
        self.assertEqual(self.meta["excluded"]["outfit_outside_allowlist"], 2)

    def test_index_has_no_adult_category_or_field(self) -> None:
        raw = json.dumps(self.index, ensure_ascii=False)
        for token in ("sexy", "pair", "内衣", "泳装", "性感", "adult"):
            self.assertNotIn(token, raw)
        for item in self.index["poses"]:
            self.assertEqual(item["people"], 1)
            self.assertFalse(item["commercial_use"])

    def test_loader_rejects_injected_adult_flag(self) -> None:
        data = json.loads(json.dumps(self.index))
        data["poses"][0]["adult"] = False
        self._expect_library_error(data)

    def test_loader_rejects_injected_category(self) -> None:
        data = json.loads(json.dumps(self.index))
        data["poses"][0]["category"]["id"] = "sexy"
        self._expect_library_error(data)

    def test_loader_rejects_multi_person(self) -> None:
        data = json.loads(json.dumps(self.index))
        data["poses"][0]["people"] = 2
        self._expect_library_error(data)

    def _expect_library_error(self, data: dict) -> None:
        path = self.tmp / "tampered.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        with self.assertRaises(SkillError) as ctx:
            Library.load(path)
        self.assertEqual(ctx.exception.code, LIBRARY_UNAVAILABLE)

    def test_no_runtime_switch_exists(self) -> None:
        config = Config.from_env({"ADULT_ENABLED": "true", "ADULT": "1"})
        self.assertFalse(hasattr(config, "adult_enabled"))
        self.assertNotIn("adult", Config.__dataclass_fields__)
        source = Path(__file__).resolve().parent.parent / "poseoutfit"
        for path in source.glob("*.py"):
            self.assertNotIn("ADULT_ENABLED", path.read_text(encoding="utf-8"), path.name)

    def test_adult_category_request_is_indistinguishable(self) -> None:
        envelope = self.call("sample_pose_options", session_id=self.sid, category_id="sexy")
        self.assertFalse(envelope["ok"])
        self.assertEqual(envelope["error"]["code"], "CATEGORY_EMPTY")
        message = envelope["error"]["message"]
        for token in ("未启用", "开启", "成人", "性感", "换一批"):
            self.assertNotIn(token, message)

    def test_adult_outfit_category_request(self) -> None:
        self.pick_pose("full")
        self.assertEqual(
            self.error("sample_outfit_options", session_id=self.sid, category_id="内衣"), "CATEGORY_EMPTY"
        )


class CommercialLicenseTests(SkillTestCase):
    def _commercial_skill(self) -> Skill:
        config = Config(
            index_path=self.index_path,
            state_dir=self.tmp / "state",
            renderer="mock",
            deployment="commercial",
            pose_library="upstream",
        )
        return Skill(config)

    def test_pose_library_blocked_for_commercial(self) -> None:
        skill = self._commercial_skill()
        session_id = skill.call("start_pose_task", {})["data"]["session_id"]
        for tool, args in (
            ("get_pose_categories", {"session_id": session_id}),
            ("sample_pose_options", {"session_id": session_id, "category_id": "full"}),
        ):
            envelope = skill.call(tool, args)
            self.assertFalse(envelope["ok"])
            self.assertEqual(envelope["error"]["code"], "LICENSE_BLOCKED")
        envelope = skill.call("start_pose_task", {})
        self.assertTrue(envelope["ok"])

    def test_own_library_requires_replaced_index(self) -> None:
        config = Config(
            index_path=self.index_path,
            state_dir=self.tmp / "state",
            renderer="mock",
            deployment="commercial",
            pose_library="own",
        )
        with self.assertRaises(SkillError) as ctx:
            Skill(config)
        self.assertEqual(ctx.exception.code, LIBRARY_UNAVAILABLE)

    def test_outfit_library_available_for_commercial(self) -> None:
        skill = self._commercial_skill()
        session_id = skill.call("start_pose_task", {})["data"]["session_id"]
        # 姿势被拦，但服装接口本身不因商用而报授权错误
        envelope = skill.call("get_outfit_categories", {"session_id": session_id})
        self.assertFalse(envelope["ok"])
        self.assertEqual(envelope["error"]["code"], "INVALID_STATE")


if __name__ == "__main__":
    unittest.main()
