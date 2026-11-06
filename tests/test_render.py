from __future__ import annotations

import json
import os
import time
import unittest
from unittest.mock import patch

from poseoutfit.errors import SkillError
from poseoutfit.render.host import HostProvider
from poseoutfit.render.mock import MockProvider
from poseoutfit.tools import Skill

from .support import SkillTestCase

PNG_1PX = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00"
    b"\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00"
    b"\x00\x00IEND\xaeB`\x82"
)


class RenderTests(SkillTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.provider = MockProvider(self.config, delay_seconds=0.05)
        self.skill = Skill(self.config, provider=self.provider)
        self.sid = self.ok("start_pose_task")["session_id"]

    def _prepare(self, description: str = "短黑发，米色风衣") -> None:
        self.pick_pose("full")
        self.pick_outfit("春")
        self.ok("receive_subject", session_id=self.sid, description=description)
        self.ok("set_spec", session_id=self.sid)

    def _job(self, run_id: str) -> dict:
        return json.loads(self.provider._path(run_id).read_text(encoding="utf-8"))

    def test_confirm_is_idempotent_while_running(self) -> None:
        slow = MockProvider(self.config, delay_seconds=5)
        skill = Skill(self.config, provider=slow)
        session_id = skill.call("start_pose_task", {})["data"]["session_id"]
        skill.call("sample_pose_options", {"session_id": session_id, "category_id": "full"})
        skill.call("select_pose", {"session_id": session_id, "ref": 1})
        skill.call("sample_outfit_options", {"session_id": session_id, "category_id": "春"})
        skill.call("select_outfit", {"session_id": session_id, "ref": 1})
        skill.call("receive_subject", {"session_id": session_id, "description": "短黑发"})
        skill.call("set_spec", {"session_id": session_id})
        first = skill.call("confirm_and_render", {"session_id": session_id, "confirmed": True})
        second = skill.call("confirm_and_render", {"session_id": session_id, "confirmed": True})
        self.assertTrue(first["ok"] and second["ok"])
        self.assertEqual(first["data"]["run_id"], second["data"]["run_id"])
        status = skill.call("get_render_status", {"session_id": session_id})
        self.assertEqual(status["data"]["status"], "RUNNING")

    def test_completed_then_duplicate_confirm(self) -> None:
        self._prepare()
        run = self.ok("confirm_and_render", session_id=self.sid, confirmed=True)
        time.sleep(0.1)
        status = self.ok("get_render_status", session_id=self.sid)
        self.assertEqual(status["status"], "COMPLETED")
        self.assertTrue(status["images"][0]["url"].startswith("data:image/svg+xml;base64,"))
        envelope = self.call("confirm_and_render", session_id=self.sid, confirmed=True)
        self.assertFalse(envelope["ok"])
        self.assertEqual(envelope["error"]["code"], "ALREADY_COMPLETED")
        self.assertTrue(envelope["error"]["details"]["render"]["images"])

    def test_prompt_is_composed_with_reference_order(self) -> None:
        self._prepare()
        run = self.ok("confirm_and_render", session_id=self.sid, confirmed=True)
        job = self._job(run["run_id"])
        prompt = job["spec"]["prompt"]
        self.assertEqual(prompt["reference_order"], ["pose", "outfit"])
        self.assertIn("blank body", prompt["positive"])
        self.assertIn("image 2 = garment design", prompt["positive"])
        self.assertIn("nsfw", prompt["negative"])
        self.assertIn("SPR-", job["assets"]["outfit"]["id"])

    def test_prompt_reference_order_with_subject_image(self) -> None:
        image_path = self.tmp / "subject.png"
        image_path.write_bytes(PNG_1PX)
        self.pick_pose("full")
        self.pick_outfit("春")
        self.ok("receive_subject", session_id=self.sid, image={"path": str(image_path)})
        self.ok("set_spec", session_id=self.sid)
        run = self.ok("confirm_and_render", session_id=self.sid, confirmed=True)
        job = self._job(run["run_id"])
        self.assertEqual(job["spec"]["prompt"]["reference_order"], ["subject", "outfit", "pose"])
        self.assertEqual(job["assets"]["subject"]["kind"], "image")

    def test_attribution_returned(self) -> None:
        self._prepare()
        self.ok("confirm_and_render", session_id=self.sid, confirmed=True)
        time.sleep(0.1)
        status = self.ok("get_render_status", session_id=self.sid)
        self.assertEqual(status["attribution"]["pose"]["author"], "ギア")
        self.assertEqual(status["attribution"]["pose"]["license"], "upstream-noncommercial")
        self.assertEqual(status["attribution"]["outfit"]["license"], "reference-only")

    def test_host_provider_requires_command(self) -> None:
        provider = HostProvider(self.config)
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SkillError) as ctx:
                provider.submit({}, {}, "key")
        self.assertEqual(ctx.exception.code, "RENDER_FAILED")

    def test_unknown_run_fails(self) -> None:
        self._prepare()
        run = self.ok("confirm_and_render", session_id=self.sid, confirmed=True)
        self.provider._path(run["run_id"]).unlink()
        time.sleep(0.1)
        status = self.ok("get_render_status", session_id=self.sid)
        self.assertEqual(status["status"], "FAILED")
        self.ok("go_back", session_id=self.sid, target="spec_confirm")
        retry = self.ok("confirm_and_render", session_id=self.sid, confirmed=True)
        self.assertTrue(retry["run_id"])


if __name__ == "__main__":
    unittest.main()
