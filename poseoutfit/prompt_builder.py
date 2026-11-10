from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence

BASE_NEGATIVE = (
    "畸形，坏手，多手指，扭曲肢体，模糊，水印，文字，低质量, "
    "deformed, bad hands, extra fingers, distorted limbs, blurry, watermark, text, low quality, "
    "mannequin, blank body, nsfw, nude, lingerie, swimsuit, explicit"
)

BASE_QUALITY = "high quality, detailed, coherent anatomy, natural proportions"

STYLE_BUNDLES = {
    "anime": {
        "positive": "anime illustration, clean line art, cel shading, flat colors, 2D artwork",
        "negative": "photorealistic, realistic skin texture, photograph, live action, 3d render",
    },
    "photo": {
        "positive": "photorealistic, natural lighting, detailed skin texture, sharp focus",
        "negative": "anime, cartoon, illustration, 3d render, line art, sketch",
    },
    "3d": {
        "positive": "3d render, cg, volumetric lighting, detailed materials",
        "negative": "photograph, anime, flat illustration, 2d",
    },
}

STYLE_ALIASES = {
    "photoreal": "photo",
    "photorealistic": "photo",
    "realistic": "photo",
    "real": "photo",
    "illustration": "anime",
    "cartoon": "anime",
    "2d": "anime",
    "cg": "3d",
}

POSE_REFERENCE_RULE = (
    "use the pose reference only for body pose and framing; "
    "the body pose must match the pose reference exactly; "
    "do not reuse the body pose or stance from the identity reference; "
    "do not render the pose reference's blank body or mannequin"
)

POSE_TOKEN_EN = {
    "站立": "standing",
    "回眸": "looking back over the shoulder",
    "顾盼": "glancing",
    "双手": "both hands",
    "双臂": "both arms",
    "单臂": "one arm",
    "上举": "raised up",
    "伸展": "stretched out",
    "后展": "extended backward",
    "挺胸": "chest out",
    "手扶腰": "hand on hip",
    "扶腰": "hand on hip",
    "撩发": "hand in hair",
    "扶发": "hand in hair",
    "抱头": "hands behind head",
    "跪立": "kneeling",
    "坐姿": "sitting",
    "蹲姿": "squatting",
    "趴卧": "lying prone",
    "俯卧": "lying prone",
    "仰卧": "lying supine",
    "侧卧": "lying on the side",
    "前倾": "leaning forward",
    "后仰": "leaning back",
    "扭身": "twisted torso",
    "抬腿": "one leg raised",
    "单腿": "one leg",
    "双腿": "both legs",
    "交叉": "crossed",
    "侧坐": "side sitting",
    "女孩坐": "side sitting",
    "摆胯": "hip sway",
    "支撑": "supported on one hand",
    "下垂": "arms down",
    "斜向前伸": "legs extended diagonally",
    "手抚脚踝": "hand touching the ankle",
}


def pose_action_hint(label: str) -> str:
    hits = [value for token, value in POSE_TOKEN_EN.items() if token in (label or "")]
    return ", ".join(dict.fromkeys(hits))

FOOTWEAR_CLAUSE = (
    "if the soles of the shoes are visible, render the outsole facing the camera, not the upper"
)
FOOTWEAR_NEGATIVE = "wrong shoe orientation, shoe upper where the sole should be"


ACCESSORY_KINDS = {
    "beret": "headwear",
    "hat": "headwear",
    "cap": "headwear",
    "beanie": "headwear",
    "headband": "headwear",
    "headscarf": "headwear",
    "sunglasses": "eyewear",
    "glasses": "eyewear",
    "goggles": "eyewear",
    "bag": "bag",
    "handbag": "bag",
    "tote": "bag",
    "backpack": "bag",
    "purse": "bag",
    "scarf": "scarf",
    "shawl": "scarf",
    "gloves": "gloves",
    "earrings": "jewelry",
    "necklace": "jewelry",
    "bracelet": "jewelry",
    "ring": "jewelry",
    "belt": "belt",
}

ACCESSORY_PLACEMENT = {
    "headwear": "wear the %s on the head, on top of the hair, and keep it clearly visible",
    "eyewear": "wear the %s on the face",
    "bag": "carry the %s",
    "scarf": "wear the %s around the neck",
    "gloves": "wear the %s on both hands",
    "jewelry": "wear the %s",
    "belt": "wear the %s at the waist",
}


def accessory_tokens(keywords: str):
    text = " %s " % (keywords or "").lower()
    found = []
    for token, kind in ACCESSORY_KINDS.items():
        if re.search(r"\b%s\b" % re.escape(token), text):
            found.append((token, kind))
    return found


def accessory_clauses(keywords: str):
    found = accessory_tokens(keywords)
    if not found:
        return None, None
    clauses = [ACCESSORY_PLACEMENT[kind] % token for token, kind in found]
    line = "ACCESSORIES: " + "; ".join(clauses) + "; do not omit any listed accessory."
    headwear = [token for token, kind in found if kind == "headwear"]
    negative = None
    if headwear:
        negative = ", ".join("missing %s, bare head, no hat" % token for token in headwear)
    return line, negative


LOWER_BODY_TOKENS = {
    "skirt", "skirts", "pants", "trousers", "jeans", "shorts", "leggings",
    "tights", "socks", "stockings", "culottes",
}
SHOE_TOKENS = {
    "boots", "boot", "sneakers", "sneaker", "heels", "heel", "pumps", "pump",
    "sandals", "sandal", "shoes", "shoe", "loafers", "loafer", "flats", "slippers", "slipper",
}
DRESS_TOKENS = {"dress", "dresses", "gown", "jumpsuit", "overalls", "romper"}

_LOWER_PATTERN = re.compile(
    r"\b(%s)\b" % "|".join(sorted(map(re.escape, LOWER_BODY_TOKENS | SHOE_TOKENS), key=len, reverse=True)),
    re.IGNORECASE,
)


def filter_outfit_keywords(keywords: str) -> tuple:
    """半身构图时移除下半身/鞋类关键词，保留上衣、外套与连衣裙。"""
    dropped = []

    def _drop(match):
        dropped.append(match.group(0))
        return " "

    filtered = _LOWER_PATTERN.sub(_drop, keywords or "")
    filtered = re.sub(r"\s+", " ", filtered)
    filtered = re.sub(r"\s*,\s*", ", ", filtered).strip(" ,")
    if not filtered:
        filtered = keywords
    return filtered, dropped


def normalize_style(value: Optional[str]) -> str:
    style = (value or "photo").strip().lower()
    style = STYLE_ALIASES.get(style, style)
    return style if style in STYLE_BUNDLES else "photo"


def build_prompts(
    pose: dict,
    outfit: Optional[dict],
    subject_description: Optional[str],
    has_subject_image: bool,
    style: str = "photo",
    include_outfit_image: bool = True,
    risks: Sequence[str] = (),
    subject_scope: str = "full",
) -> Dict[str, object]:
    style = normalize_style(style)
    bundle = STYLE_BUNDLES[style]

    include_outfit = bool(outfit and include_outfit_image)
    scope = subject_scope if subject_scope in ("face", "upper", "full") else "none"
    has_body_subject = has_subject_image and scope in ("upper", "full")
    framing = "bust" if (pose.get("category") or {}).get("id") == "bust" else "full"

    # 半身：pose 第 1（构图），subject 第 2（身份），outfit 最后（版型）
    # 全身：subject → outfit → pose（保持原策略）
    if framing == "bust":
        order = ["pose"]
        if has_subject_image:
            order.append("subject")
        if include_outfit:
            order.append("outfit")
    else:
        if has_body_subject:
            order = ["subject"]
        elif has_subject_image:
            order = ["pose"]
        else:
            order = ["pose"]
        if include_outfit:
            order.append("outfit")
        if "pose" not in order:
            order.append("pose")
        if has_subject_image and "subject" not in order:
            order.append("subject")

    roles = {name: index for index, name in enumerate(order, 1)}
    pose_idx = roles["pose"]

    label = str(pose.get("label", "")).strip()
    action = pose_action_hint(label)

    lines: List[str] = []
    pose_bits = [str(pose["prompt_snippet"]).strip()]
    if action:
        pose_bits.append(action)
    if label:
        pose_bits.append("pose: %s" % label)
    lines.append("POSE: " + ", ".join(pose_bits))
    lines.append(
        "BODY LOCK: the body pose, limb positions and camera framing must match image %d exactly." % pose_idx
    )
    if framing == "bust":
        lines.append(
            "FRAMING: upper-body portrait, crop at the waist; do not show legs, feet, or lower-body clothing."
        )
    if has_subject_image:
        lines.append(
            "SUBJECT: image %d provides the face and identity only; do not copy its body pose, stance or framing."
            % roles["subject"]
        )
    if has_body_subject:
        lines.append(
            "PROPORTIONS: keep the body proportions, head-to-body ratio, shoulder-to-hip ratio and body type "
            "of image %d; the pose reference defines joint positions and framing only." % roles["subject"]
        )
    elif has_subject_image:
        lines.append(
            "PROPORTIONS: the subject image provides the face only; take the body proportions and body type "
            "from image %d." % roles["pose"]
        )
    else:
        lines.append("PROPORTIONS: take the body proportions and body type from image %d." % roles["pose"])
    if subject_description:
        lines.append('SUBJECT DESCRIPTION: "%s"' % subject_description)
    accessory_negative = None
    if outfit:
        accessory_line, accessory_negative = accessory_clauses(str(outfit.get("keywords", "")))
        if accessory_line:
            lines.append(accessory_line)
    if outfit:
        keywords = str(outfit["keywords"]).strip()
        if framing == "bust":
            keywords, _ = filter_outfit_keywords(keywords)
        if include_outfit:
            lines.append(
                "OUTFIT: %s. Use image %d for the garment design and fit; restyle it into the target art style; "
                "do not copy its photographic texture or lighting." % (keywords, roles["outfit"])
            )
        else:
            lines.append("OUTFIT: %s (text only; no reference image)" % keywords)
        if framing == "bust":
            lines.append(
                "GARMENT: follow the upper-body portion of the garment; do not extend the frame to show lower-body clothing or feet."
            )
        else:
            lines.append(
                "GARMENT: follow the garment length and silhouette described above; "
                "do not change the body proportions to fit the garment."
            )
    style_line = "STYLE: " + bundle["positive"] + "."
    if has_subject_image:
        style_line += " Match the rendering style of image %d." % roles["subject"]
    lines.append(style_line)
    lines.append("QUALITY: " + BASE_QUALITY)
    if outfit:
        found = accessory_tokens(str(outfit.get("keywords", "")))
        if found:
            checks = "; ".join("the %s must be clearly visible" % token for token, _ in found)
            lines.append("ACCESSORY CHECK: " + checks + ".")
    if "FOOTWEAR_ORIENTATION" in risks:
        lines.append("FOOTWEAR: " + FOOTWEAR_CLAUSE)
    roles_text = {}
    if "pose" in roles:
        roles_text["pose"] = "image %d = body pose and framing only" % roles["pose"]
    if "subject" in roles:
        roles_text["subject"] = "image %d = face, identity, body proportions and rendering style" % roles["subject"]
    if "outfit" in roles:
        roles_text["outfit"] = "image %d = garment design and fit, restyled to the target art style" % roles["outfit"]
    lines.append(
        "REFERENCE ROLES: "
        + "; ".join(roles_text[name] for name in order)
        + "."
    )
    lines.append("Do not render the pose reference's blank body or mannequin.")

    negative = BASE_NEGATIVE + ", " + bundle["negative"]
    if has_body_subject:
        negative += ", different body proportions, elongated limbs, oversized head, short legs"
    if framing == "bust":
        negative += ", full body, legs, feet, lower body, long shot, wide shot"
    if style == "anime" and include_outfit:
        negative += ", photographic outfit texture, copying the outfit photo's photographic style"
    if accessory_negative:
        negative += ", " + accessory_negative
    if "FOOTWEAR_ORIENTATION" in risks:
        negative = negative + ", " + FOOTWEAR_NEGATIVE

    return {
        "positive": "\n".join(lines),
        "negative": negative,
        "reference_hint": lines[-2],
        "reference_order": order,
        "style": style,
        "framing": framing,
        "include_outfit_image": include_outfit,
    }
