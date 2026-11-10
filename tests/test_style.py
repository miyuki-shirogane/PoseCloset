from __future__ import annotations

import json
import unittest

from .support import SkillTestCase
from .test_render import PNG_1PX


class StyleTests(SkillTestCase):
    def _reach_spec(self) -> None:
        self.pick_pose("full")
        self.pick_outfit("春")
        self.ok("receive_subject", session_id=self.sid, description="短黑发，米色风衣")

    def _job(self, run_id: str) -> dict:
        return json.loads(self.skill.provider._path(run_id).read_text(encoding="utf-8"))

    def test_anime_style_with_outfit_reference(self) -> None:
        self._reach_spec()
        data = self.ok("set_spec", session_id=self.sid, style="anime")
        self.assertEqual(data["spec"]["style"], "anime")
        codes = {risk["code"] for risk in data["risks"]}
        self.assertIn("STYLE_TRANSFER", codes)
        run = self.ok("confirm_and_render", session_id=self.sid, confirmed=True)
        job = self._job(run["run_id"])
        prompt = job["spec"]["prompt"]
        self.assertEqual(prompt["style"], "anime")
        self.assertIn("anime illustration", prompt["positive"])
        self.assertIn("photorealistic", prompt["negative"])
        self.assertIn("photographic outfit texture", prompt["negative"])
        self.assertEqual(prompt["reference_order"], ["pose", "outfit"])
        self.assertTrue(job["assets"]["outfit"]["ref_url"].startswith("https://"))
        self.assertFalse(job["assets"]["outfit"]["omitted"])

    def test_body_subject_uses_subject_proportions(self) -> None:
        image_path = self.tmp / "subject.png"
        image_path.write_bytes(PNG_1PX)
        self.pick_pose("full")
        self.pick_outfit("春")
        self.ok("receive_subject", session_id=self.sid, image={"path": str(image_path)}, scope="full")
        self.ok("set_spec", session_id=self.sid, style="anime")
        run = self.ok("confirm_and_render", session_id=self.sid, confirmed=True)
        job = self._job(run["run_id"])
        prompt = job["spec"]["prompt"]
        self.assertEqual(prompt["reference_order"], ["subject", "outfit", "pose"])
        self.assertIn("head-to-body ratio", prompt["positive"])
        self.assertIn("of image 1", prompt["positive"])
        self.assertIn("must match image 3 exactly", prompt["positive"])
        self.assertIn("different body proportions", prompt["negative"])

    def test_face_subject_uses_pose_proportions(self) -> None:
        image_path = self.tmp / "face.png"
        image_path.write_bytes(PNG_1PX)
        self.pick_pose("full")
        self.pick_outfit("春")
        self.ok("receive_subject", session_id=self.sid, image={"path": str(image_path)}, scope="face")
        self.ok("set_spec", session_id=self.sid, style="anime")
        run = self.ok("confirm_and_render", session_id=self.sid, confirmed=True)
        job = self._job(run["run_id"])
        prompt = job["spec"]["prompt"]
        self.assertEqual(prompt["reference_order"], ["pose", "outfit", "subject"])
        self.assertIn("subject image provides the face only", prompt["positive"])
        self.assertIn("body proportions and body type from image 1", prompt["positive"])

    def test_invalid_subject_scope(self) -> None:
        image_path = self.tmp / "subject.png"
        image_path.write_bytes(PNG_1PX)
        self.pick_pose("full")
        self.pick_outfit("春")
        self.assertEqual(
            self.error("receive_subject", session_id=self.sid, image={"path": str(image_path)}, scope="hand"),
            "INVALID_INPUT",
        )

    def test_bust_pose_puts_pose_first_and_filters_lower_body(self) -> None:
        image_path = self.tmp / "subject.png"
        image_path.write_bytes(PNG_1PX)
        self.pick_pose("bust")
        self.ok("sample_outfit_options", session_id=self.sid, category_id="春")
        self.ok("select_outfit", session_id=self.sid, ref=1)
        self.ok(
            "receive_subject",
            session_id=self.sid,
            image={"path": str(image_path)},
            scope="full",
            subject_style="anime",
        )
        data = self.ok("set_spec", session_id=self.sid, style="anime")
        codes = {risk["code"] for risk in data["risks"]}
        self.assertIn("FRAMING_CONFLICT", codes)
        self.assertIn("OUTFIT_TRIMMED", codes)
        run = self.ok("confirm_and_render", session_id=self.sid, confirmed=True)
        job = self._job(run["run_id"])
        prompt = job["spec"]["prompt"]
        self.assertEqual(prompt["reference_order"], ["pose", "subject", "outfit"])
        self.assertIn("FRAMING: upper-body portrait", prompt["positive"])
        self.assertIn("upper-body portion", prompt["positive"])
        self.assertNotIn("skirt", prompt["positive"].lower())
        self.assertIn("white shirt", prompt["positive"].lower())
        self.assertIn("full body", prompt["negative"].lower())

    def test_photo_style_keeps_outfit_image(self) -> None:
        self._reach_spec()
        self.ok("set_spec", session_id=self.sid, style="photo")
        run = self.ok("confirm_and_render", session_id=self.sid, confirmed=True)
        job = self._job(run["run_id"])
        prompt = job["spec"]["prompt"]
        self.assertEqual(prompt["reference_order"], ["pose", "outfit"])
        self.assertTrue(job["assets"]["outfit"]["ref_url"].startswith("https://"))
        self.assertIn("anime", prompt["negative"])

    def test_style_alias_is_normalized(self) -> None:
        self._reach_spec()
        data = self.ok("set_spec", session_id=self.sid, style="photoreal")
        self.assertEqual(data["spec"]["style"], "photo")

    def test_invalid_style_rejected(self) -> None:
        self._reach_spec()
        self.assertEqual(self.error("set_spec", session_id=self.sid, style="cyberpunk"), "INVALID_INPUT")

    def test_footwear_risk_detected(self) -> None:
        risks = self.skill._risks(
            {"label": "俯卧・以臂枕头", "subcategory": "趴卧"},
            {"keywords": "dress shirt white socks sneakers bag sunglasses"},
            {"style": "photo"},
        )
        self.assertIn("FOOTWEAR_ORIENTATION", {risk["code"] for risk in risks})

    def test_footwear_risk_absent_without_shoes(self) -> None:
        risks = self.skill._risks(
            {"label": "俯卧・以臂枕头", "subcategory": "趴卧"},
            {"keywords": "white shirt denim skirt"},
            {"style": "photo"},
        )
        self.assertNotIn("FOOTWEAR_ORIENTATION", {risk["code"] for risk in risks})

    def test_footwear_risk_absent_for_standing(self) -> None:
        risks = self.skill._risks(
            {"label": "站立・双臂后展", "subcategory": "站姿"},
            {"keywords": "white sneakers"},
            {"style": "photo"},
        )
        self.assertNotIn("FOOTWEAR_ORIENTATION", {risk["code"] for risk in risks})


if __name__ == "__main__":
    unittest.main()


class AccessoryPromptTests(unittest.TestCase):
    def test_headwear_and_bag_extracted(self) -> None:
        from poseoutfit.prompt_builder import accessory_clauses

        line, negative = accessory_clauses("khaki blouse beige coat brown tights bag beret")
        self.assertIn("ACCESSORIES", line)
        self.assertIn("beret on the head", line)
        self.assertIn("carry the bag", line)
        self.assertIn("missing beret", negative)

    def test_no_accessory_returns_none(self) -> None:
        from poseoutfit.prompt_builder import accessory_clauses

        self.assertEqual(accessory_clauses("white shirt denim skirt"), (None, None))

    def test_build_prompts_includes_accessory_line(self) -> None:
        from poseoutfit.prompt_builder import build_prompts

        pose = {"prompt_snippet": "full body shot", "label": "站立", "subcategory": "站姿"}
        outfit = {"keywords": "beige coat beret"}
        result = build_prompts(pose, outfit, None, False, style="anime", include_outfit_image=False)
        self.assertIn("ACCESSORIES:", result["positive"])
        self.assertIn("beret on the head", result["positive"])
        self.assertIn("missing beret", result["negative"])
