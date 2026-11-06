#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from poseoutfit.build import build_index, write_index  # noqa: E402
from poseoutfit.errors import SkillError  # noqa: E402
from poseoutfit.library import Library  # noqa: E402

POSE_URL = "https://cdn.jsdelivr.net/gh/wzc520pyfm/gen-ai-pose-image@main/data/catalog.json"
COSTUME_URL = "https://cdn.jsdelivr.net/gh/wzc520pyfm/gen-ai-pose-image@main/data/costumes.json"


def load_source(source: str) -> Any:
    if source.startswith("http://") or source.startswith("https://"):
        request = Request(source, headers={"User-Agent": "pose-outfit-skill/1.0"})
        with urlopen(request, timeout=90) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    return json.loads(Path(source).read_text(encoding="utf-8"))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="从上游 catalog 生成过滤后的素材索引（不下载图片）")
    parser.add_argument("--pose-source", default=POSE_URL, help="上游姿势 catalog（URL 或本地路径）")
    parser.add_argument("--costume-source", default=COSTUME_URL, help="上游服装 catalog（URL 或本地路径）")
    parser.add_argument("--out-index", default=str(ROOT / "index" / "pose_outfit_index.json"))
    parser.add_argument("--out-meta", default=str(ROOT / "index" / "catalog_meta.json"))
    parser.add_argument("--check", action="store_true", help="只校验现有索引，不重新生成")
    ns = parser.parse_args(argv)

    try:
        if ns.check:
            library = Library.load(Path(ns.out_index))
            print(json.dumps({"ok": True, "poses": len(library.poses), "outfits": len(library.outfits)}, ensure_ascii=False))
            return 0

        pose_catalog = load_source(ns.pose_source)
        costume_catalog = load_source(ns.costume_source)
        index, meta = build_index(pose_catalog, costume_catalog)
        write_index(index, meta, Path(ns.out_index), Path(ns.out_meta))
        Library.load(Path(ns.out_index))
        print(
            json.dumps(
                {"ok": True, "poses": len(index["poses"]), "outfits": len(index["outfits"]), "excluded": meta["excluded"]},
                ensure_ascii=False,
            )
        )
        return 0
    except SkillError as exc:
        print(json.dumps({"ok": False, "error": exc.to_dict()}, ensure_ascii=False), file=sys.stderr)
        return 1
    except Exception as exc:  # 网络或文件错误
        print(json.dumps({"ok": False, "error": {"message": str(exc)}}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
