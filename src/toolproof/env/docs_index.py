"""BM25 search over the policy and FAQ documents in ``data/docs/``.

Each document is split into sections at ``## `` headings; sections are the unit of retrieval,
so a result snippet contains a whole rule rather than a fragment.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from toolproof.paths import docs_dir

TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORD_TEXT = (
    "a an and are as at be by can do does for from how i if in is it its my of on or our "
    "so that the their there this to was we what when which who will with you your"
)
STOPWORDS = frozenset(_STOPWORD_TEXT.split())
SNIPPET_CHARS = 700
K1 = 1.5
B = 0.75


def tokenize(text: str) -> list[str]:
    tokens = []
    for token in TOKEN_RE.findall(text.lower()):
        if token in STOPWORDS:
            continue
        if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]  # crude plural folding: refunds -> refund
        tokens.append(token)
    return tokens


@dataclass(frozen=True)
class DocChunk:
    doc_id: str
    title: str
    section: str
    text: str
    term_counts: Counter[str]
    length: int


def split_document(doc_id: str, markdown: str) -> list[DocChunk]:
    title = doc_id
    sections: list[tuple[str, list[str]]] = [("Overview", [])]
    for line in markdown.replace("\r\n", "\n").split("\n"):
        if line.startswith("# "):
            title = line[2:].strip()
        elif line.startswith("## "):
            sections.append((line[3:].strip(), []))
        else:
            sections[-1][1].append(line)
    chunks = []
    for section, lines in sections:
        body = "\n".join(lines).strip()
        if not body:
            continue
        tokens = tokenize(f"{title} {title} {section} {body}")  # title counted twice: field boost
        chunks.append(
            DocChunk(
                doc_id=doc_id,
                title=title,
                section=section,
                text=body,
                term_counts=Counter(tokens),
                length=len(tokens),
            )
        )
    return chunks


class DocsIndex:
    def __init__(self, chunks: list[DocChunk]) -> None:
        self.chunks = chunks
        self.doc_ids = sorted({chunk.doc_id for chunk in chunks})
        self._doc_freq: Counter[str] = Counter()
        for chunk in chunks:
            self._doc_freq.update(chunk.term_counts.keys())
        self._avg_length = sum(c.length for c in chunks) / len(chunks) if chunks else 0.0

    @classmethod
    def load(cls, directory: Path) -> DocsIndex:
        chunks: list[DocChunk] = []
        for path in sorted(directory.glob("*.md")):
            chunks.extend(split_document(path.stem, path.read_text(encoding="utf-8")))
        return cls(chunks)

    def _idf(self, term: str) -> float:
        n = len(self.chunks)
        df = self._doc_freq.get(term, 0)
        return math.log(1 + (n - df + 0.5) / (df + 0.5))

    def score(self, query_terms: list[str], chunk: DocChunk) -> float:
        total = 0.0
        for term in query_terms:
            tf = chunk.term_counts.get(term, 0)
            if tf == 0:
                continue
            norm = K1 * (1 - B + B * chunk.length / self._avg_length)
            total += self._idf(term) * tf * (K1 + 1) / (tf + norm)
        return total

    def search(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        terms = tokenize(query)
        scored = [(self.score(terms, chunk), index) for index, chunk in enumerate(self.chunks)]
        ranked = sorted((item for item in scored if item[0] > 0), key=lambda x: (-x[0], x[1]))
        results = []
        for score, index in ranked[:top_k]:
            chunk = self.chunks[index]
            results.append(
                {
                    "doc_id": chunk.doc_id,
                    "title": chunk.title,
                    "section": chunk.section,
                    "snippet": chunk.text[:SNIPPET_CHARS],
                    "score": round(score, 3),
                }
            )
        return results


@lru_cache(maxsize=4)
def load_docs_index(directory: Path | None = None) -> DocsIndex:
    return DocsIndex.load(directory or docs_dir())
