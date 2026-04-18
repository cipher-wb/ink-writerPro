"""Pure-Python BM25 lexical retriever for chapter memory cards.

US-022: Zero-dependency BM25 implementation that works alongside the FAISS
semantic index.  Used by :class:`SemanticChapterRetriever` to build a hybrid
retriever with reciprocal rank fusion.

Chinese text is tokenised by falling back to a character-level split (each
CJK character is one token) because most chapter summaries mix Chinese and
latin words.  Latin runs are treated as a single lower-cased token.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Iterable, List, Sequence

_TOKEN_SPLIT = re.compile(r"[\s，。；、！？：“”‘’（）【】《》()\[\],.;:!?'\"]+")
_LATIN_WORD = re.compile(r"[A-Za-z0-9_]+")
_CJK_CHAR = re.compile(r"[\u4e00-\u9fff]")


def tokenize(text: str) -> List[str]:
    """Very small tokeniser tuned for Chinese novel summaries.

    - splits on punctuation / whitespace
    - each CJK character becomes its own token
    - latin / digit runs become single lower-cased tokens
    """
    if not text:
        return []
    tokens: List[str] = []
    # step 1: coarse split
    chunks = _TOKEN_SPLIT.split(text)
    for chunk in chunks:
        if not chunk:
            continue
        # walk chunk, emit latin-words and cjk chars
        i = 0
        while i < len(chunk):
            m = _LATIN_WORD.match(chunk, i)
            if m:
                tokens.append(m.group(0).lower())
                i = m.end()
                continue
            ch = chunk[i]
            if _CJK_CHAR.match(ch):
                tokens.append(ch)
            # other chars ignored
            i += 1
    return tokens


@dataclass
class BM25Index:
    """Okapi BM25 with default parameters (k1=1.5, b=0.75).

    Only stores the minimum statistics needed for scoring; built once per
    retrieval context (~hundreds of chapters), so Python impl is fine.
    """

    k1: float = 1.5
    b: float = 0.75

    doc_tokens: List[List[str]] = field(default_factory=list)
    doc_freq: dict = field(default_factory=dict)
    doc_len: List[int] = field(default_factory=list)
    avgdl: float = 0.0
    n_docs: int = 0

    def fit(self, docs: Sequence[str]) -> "BM25Index":
        self.doc_tokens = [tokenize(d) for d in docs]
        self.doc_len = [len(toks) for toks in self.doc_tokens]
        self.n_docs = len(self.doc_tokens)
        self.avgdl = (sum(self.doc_len) / self.n_docs) if self.n_docs else 0.0
        self.doc_freq = {}
        for toks in self.doc_tokens:
            seen = set(toks)
            for t in seen:
                self.doc_freq[t] = self.doc_freq.get(t, 0) + 1
        return self

    def _idf(self, term: str) -> float:
        df = self.doc_freq.get(term, 0)
        if df == 0:
            return 0.0
        # standard BM25 idf with +1 smoothing (always positive)
        return math.log(1.0 + (self.n_docs - df + 0.5) / (df + 0.5))

    def score(self, query: str, doc_idx: int) -> float:
        if doc_idx < 0 or doc_idx >= self.n_docs:
            return 0.0
        q_terms = tokenize(query)
        if not q_terms:
            return 0.0
        toks = self.doc_tokens[doc_idx]
        if not toks:
            return 0.0
        tf: dict = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        dl = self.doc_len[doc_idx]
        score = 0.0
        for term in q_terms:
            if term not in tf:
                continue
            idf = self._idf(term)
            freq = tf[term]
            denom = freq + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1.0))
            score += idf * (freq * (self.k1 + 1)) / (denom or 1.0)
        return score

    def search(
        self,
        query: str,
        k: int,
        eligible: Iterable[int] | None = None,
    ) -> List[tuple]:
        """Return a list of (doc_idx, score) pairs ranked by descending score.

        - ``eligible`` lets callers restrict scoring to a subset of docs
          (used to enforce the ``before_chapter`` constraint).
        - Zero-scoring docs are dropped.
        """
        if self.n_docs == 0:
            return []
        q_terms = tokenize(query)
        if not q_terms:
            return []
        indices = list(eligible) if eligible is not None else list(range(self.n_docs))
        scored: List[tuple] = []
        for idx in indices:
            s = self.score(query, idx)
            if s > 0:
                scored.append((idx, s))
        scored.sort(key=lambda x: (-x[1], -x[0]))
        return scored[:k]
