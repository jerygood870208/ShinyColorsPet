"""Generate a review-required manifest beside externally supplied assets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from .manifest import ManifestError
from .semantic_animations import dialogue_animation_groups, dialogue_expressions, dialogue_gaze


def generate_candidate(
    skeleton: Path, atlas: Path, output: Path, character_id: str, display_name: str
) -> dict[str, Any]:
    root = output.parent.resolve()
    try:
        skeleton_name = skeleton.resolve().relative_to(root).as_posix()
        atlas_name = atlas.resolve().relative_to(root).as_posix()
    except ValueError as exc:
        raise ManifestError("output must be beside or above the assets") from exc
    data = json.loads(skeleton.read_text(encoding="utf-8-sig"))
    if ".".join(data.get("skeleton", {}).get("spine", "").split(".")[:2]) != "3.6":
        raise ManifestError("candidate generator requires Spine 3.6")
    names = sorted(data.get("animations", {}))
    groups = dialogue_animation_groups(names)
    lips = [n for n in names if n.startswith("lip_")]
    candidate: dict[str, Any] = {
        "schema_version": 1,
        "character_id": character_id,
        "display_name": display_name,
        "review": {"status": "candidate", "notes": "Review every semantic mapping and driver."},
        "spine": {
            "runtime": "3.6",
            "skeleton": skeleton_name,
            "atlas": atlas_name,
            "default_skin": "default",
            "premultiplied_alpha": False,
        },
        "channels": {"base": 0, "gesture": 1, "face": 2, "lipsync": 3, "gaze": 4},
        "animation_groups": groups,
        "expressions": dialogue_expressions(names),
        "lipsync": (
            {"driver": "animation_mix", "channel": "lipsync", "candidates": lips}
            if lips
            else {"driver": "disabled", "reason": "No lip_* candidates"}
        ),
        "gaze": dialogue_gaze(names),
        "hit_areas": {"source": "alpha_mask", "aliases": {}},
        "events": {n: n for n in sorted(data.get("events", {}))},
    }
    # Exclusive creation protects an existing reviewed manifest.
    with output.open("x", encoding="utf-8") as stream:
        yaml.safe_dump(candidate, stream, allow_unicode=True, sort_keys=False)
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("skeleton", type=Path)
    parser.add_argument("atlas", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--character-id", required=True)
    parser.add_argument("--display-name", required=True)
    args = parser.parse_args()
    generate_candidate(args.skeleton, args.atlas, args.output, args.character_id, args.display_name)
    print(f"Candidate written: {args.output}. Review, then set review.status: approved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
