import math
import re
from pathlib import Path

DEFAULT_POLICIES_DIR = Path(__file__).resolve().parent.parent / "data" / "policies"

_STOPWORDS = frozenset(
    "a an and are at be by can do does for from how i if in is it me my of on or our"
    " the that there this to we what when where which who will with you your".split()
)

# Standard BM25 defaults.
_K1 = 1.5
_B = 0.75


def _stem(word: str) -> str:
    # Just enough to match "opening" with "open" and "bikes" with "bike".
    if len(word) > 5 and word.endswith("ing"):
        return word[:-3]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _tokens(text: str) -> list[str]:
    return [_stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOPWORDS]


def _sections(policies_dir: Path) -> list[dict]:
    """One section per "## " heading; text before the first one belongs to the "# " title."""
    sections = []
    for path in sorted(Path(policies_dir).glob("*.md")):
        heading, body = None, []

        def flush():
            text = "\n".join(body).strip()
            if heading is not None and text:
                sections.append({"file": path.name, "section": heading, "text": text})

        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                flush()
                heading, body = line[3:].strip(), []
            elif line.startswith("# "):
                heading = line[2:].strip()
            else:
                body.append(line)
        flush()
    return sections


def search_policies(
    query: str, top_k: int = 3, policies_dir: Path = DEFAULT_POLICIES_DIR
) -> list[dict]:
    """Best-matching policy sections as [{"file", "section", "text"}], best first.

    Returns [] when no section shares a word with the query: the model's signal that the
    documents do not answer it.
    """
    if not isinstance(query, str):
        return []
    query_terms = set(_tokens(query))
    sections = _sections(policies_dir)
    docs = [_tokens(f"{s['section']} {s['text']}") for s in sections]
    avg_len = sum(len(d) for d in docs) / len(docs)
    doc_freq = {}
    for doc in docs:
        for term in set(doc):
            doc_freq[term] = doc_freq.get(term, 0) + 1

    scored = []
    for section, doc in zip(sections, docs):
        score = 0.0
        for term in query_terms:
            tf = doc.count(term)
            if not tf:
                continue
            idf = math.log(1 + (len(docs) - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5))
            score += idf * tf * (_K1 + 1) / (tf + _K1 * (1 - _B + _B * len(doc) / avg_len))
        if score > 0:
            scored.append((score, section))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [section for _, section in scored[:top_k]]
