"""build_polish_prompt 单元测试 — spec §5.3 + Q12 + US-007 acceptance criteria。"""

from __future__ import annotations

from ink_writer.rewrite_loop.polish_prompt import build_polish_prompt


def test_polish_prompt_contains_case_failure_pattern(sample_chapter_text, sample_case):
    prompt = build_polish_prompt(
        chapter_text=sample_chapter_text,
        case_id=sample_case["case_id"],
        case_failure_description=sample_case["failure_description"],
        case_observable=sample_case["observable"],
        related_chunks=None,
    )

    assert sample_case["case_id"] in prompt
    assert sample_case["failure_description"] in prompt
    for observable in sample_case["observable"]:
        assert observable in prompt
    assert sample_chapter_text in prompt
    assert "只重写最小必要段落" in prompt
    assert "不输出 diff" in prompt
    assert "末尾附 1 行修改说明" in prompt
    assert "不包裹 markdown" in prompt


def test_polish_prompt_handles_empty_chunks(sample_chapter_text, sample_case):
    prompt = build_polish_prompt(
        chapter_text=sample_chapter_text,
        case_id=sample_case["case_id"],
        case_failure_description=sample_case["failure_description"],
        case_observable=sample_case["observable"],
        related_chunks=None,
    )

    assert ("无相关范文" in prompt) or ("no related chunks available" in prompt)


def test_polish_prompt_includes_chunks_when_present(
    sample_chapter_text, sample_case, sample_chunks
):
    prompt = build_polish_prompt(
        chapter_text=sample_chapter_text,
        case_id=sample_case["case_id"],
        case_failure_description=sample_case["failure_description"],
        case_observable=sample_case["observable"],
        related_chunks=sample_chunks,
    )

    for chunk in sample_chunks:
        assert chunk["chunk_id"] in prompt
        # text 摘要：只要前若干字符出现即可，避免长文本断行噪声
        assert chunk["text"][:20] in prompt
