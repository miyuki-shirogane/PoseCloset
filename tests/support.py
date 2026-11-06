from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from poseoutfit.build import build_index, write_index
from poseoutfit.config import Config
from poseoutfit.tools import Skill


def _pose(pid: str, system: str, category: str, adult: bool = False, people: int = 1) -> dict:
    return {
        "id": pid,
        "system": "全身单人・标准系" if system == "full" else "上半身单人",
        "systemId": system,
        "code": pid.split("_")[-1],
        "category": category,
        "name": "姿势 %s" % pid.split("_")[-1],
        "adult": adult,
        "people": people,
        "views": [
            {
                "id": "%s_front" % pid,
                "angle": "正面",
                "angleId": "front",
                "thumb": "thumbs/%s_front.jpg" % pid,
                "full": "img/%s_front.png" % pid,
            }
        ],
    }


def _outfit(oid: str, category: str, adult: bool = False) -> dict:
    return {
        "id": oid,
        "category": category,
        "label": "服装",
        "keywords": "white shirt, denim skirt",
        "adult": adult,
        "thumb": "thumbs/%s.webp" % oid,
        "preview": "img/%s.webp" % oid,
        "full": "png/%s.png" % oid,
    }


def make_catalogs():
    poses = []
    for index in range(1, 8):
        poses.append(_pose("full_single_P%03d" % index, "full", "站姿"))
    for index in range(1, 3):
        poses.append(_pose("bust_single_P%03d" % index, "bust", "坐姿"))
    for index in range(1, 4):
        poses.append(_pose("sexy_single_P%03d" % index, "sexy", "性感・大胆系", adult=True))
    for index in range(1, 3):
        poses.append(_pose("pair_single_P%03d" % index, "pair", "贴脸系", adult=True, people=2))
    poses.append(_pose("bust_single_P099", "bust", "坐姿", adult=True))
    pose_catalog = {
        "version": 1,
        "source": "fixture",
        "upstream": "fixture",
        "origin": "https://ai-pose-gallery.anhao.app",
        "poseCount": len(poses),
        "viewCount": len(poses),
        "adultPoseCount": 6,
        "systems": [],
        "poses": poses,
    }
    outfits = []
    for index in range(1, 7):
        outfits.append(_outfit("SPR-%04d" % index, "春"))
    outfits.append(_outfit("LNG-0001", "内衣", adult=True))
    outfits.append(_outfit("SWM-0001", "泳装", adult=True))
    costume_catalog = {
        "version": 1,
        "source": "fixture",
        "origin": "https://ai-costume-gallery.pages.dev",
        "total": len(outfits),
        "categories": [],
        "costumes": outfits,
    }
    return pose_catalog, costume_catalog


class SkillTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        pose_catalog, costume_catalog = make_catalogs()
        index, meta = build_index(pose_catalog, costume_catalog)
        self.index = index
        self.meta = meta
        self.index_path = self.tmp / "index.json"
        write_index(index, meta, self.index_path, self.tmp / "meta.json")
        self.config = Config(
            index_path=self.index_path,
            state_dir=self.tmp / "state",
            renderer="mock",
            session_ttl_hours=1,
        )
        self.skill = Skill(self.config)
        self.sid = self.ok("start_pose_task")["session_id"]

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def call(self, name: str, **args):
        return self.skill.call(name, args)

    def ok(self, name: str, **args):
        envelope = self.call(name, **args)
        self.assertTrue(envelope["ok"], envelope)
        return envelope["data"]

    def error(self, name: str, **args) -> str:
        envelope = self.call(name, **args)
        self.assertFalse(envelope["ok"], envelope)
        return envelope["error"]["code"]

    def pick_pose(self, category: str = "full") -> dict:
        self.ok("sample_pose_options", session_id=self.sid, category_id=category)
        return self.ok("select_pose", session_id=self.sid, ref=1)

    def pick_outfit(self, category: str = "春") -> dict:
        self.ok("sample_outfit_options", session_id=self.sid, category_id=category)
        return self.ok("select_outfit", session_id=self.sid, ref=1)


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))
