"""Layer 5 meta-rule emergence — group similar cases via LLM and propose merges.

Pipeline:
  1. ``_candidate_clusters_by_tags`` does a cheap tag-overlap pre-filter to
     keep LLM calls bounded (skip ``sovereign`` cases + cases that already
     have a ``meta_rule_id``).
  2. Each candidate cluster of size ≥ ``min_cluster_size`` is shipped to the
     LLM with the ``emerge.txt`` prompt; the model returns a JSON verdict.
  3. Verdicts with ``similarity >= threshold`` and ``len(covered_cases) >=
     min_cluster_size`` become :class:`MetaRuleProposal` objects.
  4. :func:`write_meta_rule_proposal` persists one proposal as YAML under
     ``data/case_library/meta_rules/MR-NNNN.yaml`` (status=pending).
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Protocol

import yaml

from ink_writer.case_library.models import Case
from ink_writer.meta_rule_emergence.models import MetaRuleProposal

_PROMPT_PATH = Path(__file__).parent / "prompts" / "emerge.txt"
_DEFAULT_META_RULES_DIR = Path("data/case_library/meta_rules")
_PROPOSAL_ID_PATTERN = re.compile(r"^MR-(\d{4,})$")


class _LLMLike(Protocol):
    """Structural type for the subset of LLMClient surface we use."""

    @property
    def messages(self) -> Any: ...  # pragma: no cover — Protocol stub


def _load_prompt() -> str:
    with open(_PROMPT_PATH, encoding="utf-8") as fp:
        return fp.read()


def _case_payload(case: Case) -> dict[str, Any]:
    return {
        "case_id": case.case_id,
        "title": case.title,
        "description": case.failure_pattern.description,
        "tags": list(case.tags),
    }


def _eligible(case: Case) -> bool:
    """Skip sovereign cases and ones already attached to a meta-rule."""
    if case.sovereign:
        return False
    return not case.meta_rule_id


def _candidate_clusters_by_tags(cases: Iterable[Case]) -> list[list[Case]]:
    """Coarse pre-filter: group cases by shared tag.

    Each tag whose case set is non-trivial becomes one candidate cluster.
    A single case may appear in multiple clusters (the LLM has the final
    say on which subset is actually similar). Cases without any tag are
    skipped — there is no signal to cluster on.
    """
    by_tag: dict[str, list[Case]] = defaultdict(list)
    for case in cases:
        for tag in case.tags:
            by_tag[tag].append(case)

    clusters: list[list[Case]] = []
    seen_signatures: set[tuple[str, ...]] = set()
    for _tag, members in by_tag.items():
        if len(members) < 2:
            continue
        signature = tuple(sorted(c.case_id for c in members))
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        clusters.append(members)
    return clusters


def _parse_llm_json(raw: str) -> dict[str, Any] | None:
    """Tolerantly extract the JSON object the model emitted."""
    text = raw.strip()
    if text.startswith("```"):
        # strip ```json ... ``` fences
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match is None:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    if not isinstance(data, dict):
        return None
    return data


def _call_llm(
    *,
    llm_client: _LLMLike,
    prompt: str,
    model: str,
) -> dict[str, Any] | None:
    try:
        resp = llm_client.messages.create(
            max_tokens=1024,
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception:  # noqa: BLE001 — LLM transport failure → no proposal
        return None
    if not resp.content:
        return None
    return _parse_llm_json(resp.content[0].text or "")


def _proposal_from_verdict(
    *,
    verdict: dict[str, Any],
    cluster: list[Case],
    proposal_id: str,
    similarity_threshold: float,
    min_cluster_size: int,
) -> MetaRuleProposal | None:
    if not verdict.get("similar"):
        return None
    try:
        similarity = float(verdict.get("similarity", 0.0))
    except (TypeError, ValueError):
        return None
    if similarity < similarity_threshold:
        return None
    cluster_ids = {c.case_id for c in cluster}
    raw_covered = verdict.get("covered_cases") or []
    covered: list[str] = [
        cid for cid in raw_covered
        if isinstance(cid, str) and cid in cluster_ids
    ]
    if len(covered) < min_cluster_size:
        return None
    merged_rule = str(verdict.get("merged_rule") or "").strip()
    if not merged_rule:
        return None
    reason = str(verdict.get("reason") or "").strip()
    return MetaRuleProposal(
        proposal_id=proposal_id,
        similarity=similarity,
        merged_rule=merged_rule,
        covered_cases=covered,
        reason=reason,
    )


def _next_proposal_id(base_dir: Path = _DEFAULT_META_RULES_DIR) -> str:
    """Return ``MR-NNNN`` one above the highest existing id (or ``MR-0001``)."""
    base = Path(base_dir)
    if not base.exists():
        return "MR-0001"
    max_num = 0
    for path in base.glob("MR-*.yaml"):
        match = _PROPOSAL_ID_PATTERN.match(path.stem)
        if match is None:
            continue
        try:
            max_num = max(max_num, int(match.group(1)))
        except ValueError:
            continue
    return f"MR-{max_num + 1:04d}"


def find_similar_clusters(
    *,
    cases: Iterable[Case],
    llm_client: _LLMLike,
    min_cluster_size: int = 5,
    similarity_threshold: float = 0.80,
    model: str = "glm-4.6",
    meta_rules_dir: Path = _DEFAULT_META_RULES_DIR,
) -> list[MetaRuleProposal]:
    """Return zero or more proposals over the eligible cases.

    The function mutates nothing on disk — call :func:`write_meta_rule_proposal`
    to persist results.
    """
    eligible = [c for c in cases if _eligible(c)]
    candidate_clusters = _candidate_clusters_by_tags(eligible)
    prompt_template = _load_prompt()

    proposals: list[MetaRuleProposal] = []
    next_num = int(_next_proposal_id(meta_rules_dir).split("-")[1])

    for cluster in candidate_clusters:
        if len(cluster) < min_cluster_size:
            continue
        cases_json = json.dumps(
            [_case_payload(c) for c in cluster],
            ensure_ascii=False,
            indent=2,
        )
        prompt = prompt_template.replace("{cases_json}", cases_json)
        verdict = _call_llm(
            llm_client=llm_client,
            prompt=prompt,
            model=model,
        )
        if verdict is None:
            continue
        proposal_id = f"MR-{next_num:04d}"
        proposal = _proposal_from_verdict(
            verdict=verdict,
            cluster=cluster,
            proposal_id=proposal_id,
            similarity_threshold=similarity_threshold,
            min_cluster_size=min_cluster_size,
        )
        if proposal is None:
            continue
        proposals.append(proposal)
        next_num += 1
    return proposals


def write_meta_rule_proposal(
    *,
    proposal: MetaRuleProposal,
    base_dir: Path = _DEFAULT_META_RULES_DIR,
) -> Path:
    """Write the proposal to ``base_dir/<proposal_id>.yaml`` with ``status: pending``."""
    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    out = base / f"{proposal.proposal_id}.yaml"
    with open(out, "w", encoding="utf-8") as fp:
        yaml.safe_dump(
            proposal.to_dict(),
            fp,
            allow_unicode=True,
            sort_keys=False,
            default_flow_style=False,
        )
    return out
