"""``python -m ink_writer.meta_rule_emergence`` — Layer 5 propose CLI.

Default behaviour is dry-run (compute proposals, print summary, do not write).
Pass ``--propose`` to persist proposals as YAML under
``data/case_library/meta_rules/MR-NNNN.yaml``.
"""
from __future__ import annotations

import argparse
import os as _os_win_stdio
import sys as _sys_win_stdio
from pathlib import Path

_ink_scripts = _os_win_stdio.path.join(
    _os_win_stdio.path.dirname(_os_win_stdio.path.abspath(__file__)),
    "../../ink-writer/scripts",
)
if _os_win_stdio.path.isdir(_ink_scripts) and _ink_scripts not in _sys_win_stdio.path:
    _sys_win_stdio.path.insert(0, _ink_scripts)
try:
    from runtime_compat import enable_windows_utf8_stdio as _enable_utf8_stdio
    _enable_utf8_stdio()
except Exception:  # pragma: no cover
    pass

from ink_writer.case_library.store import CaseStore
from ink_writer.meta_rule_emergence.emerger import (
    find_similar_clusters,
    write_meta_rule_proposal,
)


def _build_llm_client() -> object:
    """Mirror scripts/corpus_chunking/cli.py — env-driven OpenAI-compat client."""
    base_url = _os_win_stdio.environ.get(
        "LLM_BASE_URL", "https://open.bigmodel.cn/api/paas/v4"
    )
    api_key = (
        _os_win_stdio.environ.get("LLM_API_KEY")
        or _os_win_stdio.environ.get("EMBED_API_KEY", "")
    )
    model = _os_win_stdio.environ.get("LLM_MODEL", "glm-4.6")
    if not api_key:
        raise RuntimeError(
            "LLM_API_KEY (or EMBED_API_KEY fallback) not set; "
            "configure ~/.claude/ink-writer/.env"
        )
    from scripts.corpus_chunking.llm_client import LLMClient

    return LLMClient(base_url=base_url, api_key=api_key, default_model=model)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ink_writer.meta_rule_emergence",
        description=(
            "Layer 5 meta-rule emergence — cluster similar active cases via "
            "LLM and write pending MetaRuleProposal YAMLs."
        ),
    )
    parser.add_argument(
        "--propose",
        action="store_true",
        help="Persist proposals to data/case_library/meta_rules/.",
    )
    parser.add_argument(
        "--min-cluster",
        type=int,
        default=5,
        help="Minimum cluster size for a proposal (default: 5).",
    )
    parser.add_argument(
        "--similarity",
        type=float,
        default=0.80,
        help="LLM similarity threshold (default: 0.80).",
    )
    parser.add_argument(
        "--library-root",
        default="data/case_library",
        help="Case library root (default: data/case_library).",
    )
    parser.add_argument(
        "--meta-rules-dir",
        default="data/case_library/meta_rules",
        help="Where MR-NNNN.yaml is read/written (default: data/case_library/meta_rules).",
    )
    parser.add_argument(
        "--model",
        default="glm-4.6",
        help="LLM model id (default: glm-4.6).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    store = CaseStore(Path(args.library_root))
    cases = list(store.iter_all())
    if not cases:
        print("提议数: 0 (no cases in library)")
        return 0

    try:
        llm_client = _build_llm_client()
    except RuntimeError as err:
        print(f"提议数: 0 ({err})")
        return 0

    proposals = find_similar_clusters(
        cases=cases,
        llm_client=llm_client,
        min_cluster_size=args.min_cluster,
        similarity_threshold=args.similarity,
        model=args.model,
        meta_rules_dir=Path(args.meta_rules_dir),
    )

    written = 0
    if args.propose:
        for proposal in proposals:
            write_meta_rule_proposal(
                proposal=proposal,
                base_dir=Path(args.meta_rules_dir),
            )
            written += 1

    print(f"提议数: {len(proposals)} (written: {written}, dry_run: {not args.propose})")
    for proposal in proposals:
        print(
            f"  {proposal.proposal_id} sim={proposal.similarity:.2f} "
            f"cases={len(proposal.covered_cases)} :: {proposal.merged_rule}"
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
