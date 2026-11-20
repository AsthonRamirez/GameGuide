"""Tokenización, BM25, fragmentación (chunking) y fusión de rankings. Sin dependencias externas."""
from __future__ import annotations
import math
import re

STOPWORDS = {
    "de", "la", "el", "los", "las", "un", "una", "unos", "unas", "y", "o", "a", "en", "por", "para",
    "con", "sin", "que", "como", "qué", "cual", "cuál", "cómo", "es", "son", "del", "al", "me", "mi",
    "tu", "se", "su", "sus", "lo", "le", "les", "sobre", "desde", "hasta", "hay", "hacer", "puedo",
    "the", "an", "and", "or", "of", "to", "in", "on", "for", "with", "how", "what", "is", "are",
    "it", "its", "this", "that", "be", "can", "you", "your", "by", "as", "at", "from",
}


def _stem(token: str) -> str:
    # Plural básico (inglés/español): "diamonds"->"diamond", "élitras"->"élitra".
    if len(token) > 4 and token.endswith("es") and token[-3] in "sxz":
        return token[:-2]
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokenize(text) -> list[str]:
    tokens = re.findall(r"[a-zA-Z0-9áéíóúñüÁÉÍÓÚÑÜ]+", str(text).lower())
    return [_stem(t) for t in tokens if len(t) > 1 and t not in STOPWORDS]


def bm25_scores(query_tokens: list[str], doc_tokens: list[list[str]], k1=1.5, b=0.75) -> list[float]:
    if not doc_tokens:
        return []
    q = set(query_tokens)
    n = len(doc_tokens)
    avgdl = sum(map(len, doc_tokens)) / max(n, 1)
    df: dict[str, int] = {}
    for toks in doc_tokens:
        for term in set(toks):
            df[term] = df.get(term, 0) + 1
    scores = []
    for toks in doc_tokens:
        freqs: dict[str, int] = {}
        for t in toks:
            freqs[t] = freqs.get(t, 0) + 1
        length, score = len(toks), 0.0
        for term in q:
            tf = freqs.get(term)
            if not tf:
                continue
            idf = math.log(1 + (n - df.get(term, 0) + 0.5) / (df.get(term, 0) + 0.5))
            score += idf * (tf * (k1 + 1) / (tf + k1 * (1 - b + b * length / max(avgdl, 1))))
        scores.append(score)
    return scores


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ0-9\"'(\[])")


def chunk_text(text: str, size: int = 800, overlap: int = 150) -> list[str]:
    """Divide en fragmentos de ~size caracteres respetando oraciones, con traslape."""
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    if not text:
        return []
    if len(text) <= size:
        return [text]
    sentences = []
    for s in _SENTENCE_SPLIT.split(text):
        # Una "oración" enorme (sin puntuación) se corta a la fuerza.
        while len(s) > size:
            sentences.append(s[:size])
            s = s[size:]
        if s:
            sentences.append(s)
    chunks, current = [], ""
    for sentence in sentences:
        if current and len(current) + 1 + len(sentence) > size:
            chunks.append(current)
            tail = current[-overlap:] if overlap else ""
            # El traslape empieza en un límite de palabra.
            tail = tail[tail.find(" ") + 1:] if " " in tail else tail
            current = (tail + " " + sentence).strip()
        else:
            current = (current + " " + sentence).strip()
    if current:
        chunks.append(current)
    return chunks


def rrf(rankings: list[list], k: int = 60) -> dict:
    """Reciprocal Rank Fusion: cada ranking es una lista de ids ordenada de mejor a peor."""
    fused: dict = {}
    for ranking in rankings:
        for pos, item in enumerate(ranking, start=1):
            fused[item] = fused.get(item, 0.0) + 1.0 / (k + pos)
    return fused
