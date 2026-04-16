#!/usr/bin/env python3
"""Generate per-checker slim review bundles from a full review bundle.

Usage:
    python3 slim_review_bundle.py --bundle full_bundle.json --checkers checker1,checker2 --outdir /tmp/

For each checker, outputs a JSON file containing only the fields that checker
needs (meta + profile-specific fields). Falls back to the full bundle on error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# Fields always preserved in every slim bundle
META_FIELDS: list[str] = [
    "chapter",
    "project_root",
    "chapter_file",
    "chapter_file_name",
    "chapter_char_count",
    "absolute_paths",
    "allowed_read_files",
    "review_policy",
]

# Per-checker profile: extra fields beyond META_FIELDS
CHECKER_PROFILES: dict[str, list[str]] = {
    "anti-detection-checker": [
        "chapter_text",
    ],
    "logic-checker": [
        "chapter_text",
        "scene_context",
        "setting_snapshots",
        "core_context",
    ],
    "outline-compliance-checker": [
        "chapter_text",
        "outline",
        "scene_context",
        "core_context",
    ],
    "continuity-checker": [
        "chapter_text",
        "previous_chapters",
        "memory_context",
        "outline",
        "narrative_commitments",
        "plot_structure_fingerprints",
    ],
    "consistency-checker": [
        "chapter_text",
        "setting_snapshots",
        "scene_context",
        "previous_chapters",
        "memory_context",
        "narrative_commitments",
        "plot_structure_fingerprints",
    ],
    "ooc-checker": [
        "chapter_text",
        "scene_context",
        "previous_chapters",
        "setting_snapshots",
    ],
    "reader-pull-checker": [
        "chapter_text",
        "reader_signal",
        "memory_context",
        "outline",
        "golden_three_contract",
    ],
}

# Conditional checkers reuse a core checker's profile
CONDITIONAL_PROFILE_MAP: dict[str, str] = {
    "golden-three-checker": "reader-pull-checker",
    "high-point-checker": "reader-pull-checker",
    "pacing-checker": "continuity-checker",
    "proofreading-checker": "anti-detection-checker",
    "reader-simulator": "reader-pull-checker",
    "emotion-curve-checker": "reader-pull-checker",
}


def resolve_profile(checker_name: str) -> list[str] | None:
    """Return the field list for a checker, or None if unknown."""
    if checker_name in CHECKER_PROFILES:
        return CHECKER_PROFILES[checker_name]
    mapped = CONDITIONAL_PROFILE_MAP.get(checker_name)
    if mapped and mapped in CHECKER_PROFILES:
        return CHECKER_PROFILES[mapped]
    return None


def slim_bundle(
    full_bundle: dict[str, Any],
    checker_name: str,
    extra_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Extract a slim bundle for the given checker.

    Returns a dict with META_FIELDS + checker-specific fields + optional extra_fields.
    Raises ValueError if the checker has no known profile.
    """
    profile_fields = resolve_profile(checker_name)
    if profile_fields is None:
        raise ValueError(f"Unknown checker: {checker_name}")

    wanted = set(META_FIELDS) | set(profile_fields)
    result = {k: v for k, v in full_bundle.items() if k in wanted}
    if extra_fields:
        result.update(extra_fields)
    return result


def generate_slim_bundles(
    bundle_path: Path,
    checkers: list[str],
    outdir: Path,
    per_checker_extras: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Path]:
    """Generate slim bundle files for each checker.

    Args:
        bundle_path: Path to the full review bundle JSON.
        checkers: List of checker names.
        outdir: Output directory for slim bundles.
        per_checker_extras: Optional dict mapping checker_name -> extra fields to inject.
            Example: {"logic-checker": {"precheck_results": {...}}}

    Returns a mapping of checker_name -> output_path.
    On per-checker failure, maps to the original full bundle path (fallback).
    """
    full_bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    chapter_padded = str(full_bundle.get("chapter", 0)).zfill(4)

    outdir.mkdir(parents=True, exist_ok=True)
    result: dict[str, Path] = {}
    extras = per_checker_extras or {}

    for checker in checkers:
        out_file = outdir / f"review_bundle_ch{chapter_padded}_{checker}.json"
        try:
            slimmed = slim_bundle(full_bundle, checker, extras.get(checker))
            out_file.write_text(
                json.dumps(slimmed, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            result[checker] = out_file
        except Exception:
            # Fallback: use original full bundle
            result[checker] = bundle_path

    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate per-checker slim review bundles")
    parser.add_argument("--bundle", required=True, help="Path to full review bundle JSON")
    parser.add_argument("--checkers", required=True, help="Comma-separated checker names")
    parser.add_argument("--outdir", required=True, help="Output directory for slim bundles")
    parser.add_argument(
        "--precheck",
        action="store_true",
        help="Run logic_precheck and inject results into logic-checker bundle",
    )
    args = parser.parse_args()

    bundle_path = Path(args.bundle)
    if not bundle_path.exists():
        print(f"ERROR: bundle not found: {bundle_path}", file=sys.stderr)
        sys.exit(1)

    checkers = [c.strip() for c in args.checkers.split(",") if c.strip()]
    outdir = Path(args.outdir)

    per_checker_extras: dict[str, dict[str, Any]] | None = None
    if args.precheck and "logic-checker" in checkers:
        try:
            from logic_precheck import run_precheck

            full_bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            chapter_text = full_bundle.get("chapter_text", "")
            character_snapshot = {
                "protagonist_snapshot": (full_bundle.get("core_context") or {}).get(
                    "protagonist_snapshot", {}
                ),
                "appearing_characters": (full_bundle.get("scene_context") or {}).get(
                    "appearing_characters", []
                ),
            }
            precheck_results = run_precheck(chapter_text, character_snapshot)
            per_checker_extras = {"logic-checker": {"precheck_results": precheck_results}}
        except Exception as e:
            print(f"WARNING: logic precheck failed, skipping: {e}", file=sys.stderr)

    result = generate_slim_bundles(bundle_path, checkers, outdir, per_checker_extras)

    # Output mapping as JSON for consumption by the workflow
    output = {checker: str(path) for checker, path in result.items()}
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
