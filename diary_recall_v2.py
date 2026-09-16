"""Гибридный поиск по дневнику (recall_v2): текст + смысл.

score = 0.6 * cosine + 0.4 * bm25minmax. Рядом со старым diary_query
ничего не меняет; деградация честная: если векторная половина недоступна,
hybrid ищет текстом и говорит об этом в поле why.
"""

from diary_search import search as search_text
from diary_validation import ValidationError
from diary_vec import search_vec

W_VECTOR, W_TEXT = 0.6, 0.4
_MODES = ("hybrid", "text", "vector")


def _normalize(scores: list[float]) -> list[float]:
    """Min-max нормировка по выдаче; все равны — все единицы."""
    low, high = min(scores, default=0.0), max(scores, default=0.0)
    if high - low <= 1e-9:
        return [1.0 for _ in scores]
    return [(value - low) / (high - low) for value in scores]


def recall_v2(diary_path, query, k=5, mode="hybrid") -> list[dict]:
    """Найти записи по дневнику: [{'id', 'score', 'why', 'snippet'}]."""
    if mode not in _MODES:
        raise ValidationError(f"'mode' должен быть одним из: {', '.join(_MODES)}")
    if not isinstance(query, str) or not query.strip():
        raise ValidationError("запрос должен быть непустой строкой")
    if mode == "text":
        return [
            dict(item, score=item["score"], why="bm25", snippet=item["snippet"])
            for item in search_text(diary_path, query, k=k)
        ]
    try:
        vector_hits = search_vec(diary_path, query, k=k)
        vector_ok = True
    except Exception:
        vector_hits, vector_ok = [], False
        if mode == "vector":
            raise
    if mode == "vector":
        return [dict(item, why="cosine", snippet="") for item in vector_hits]
    text_hits = search_text(diary_path, query, k=k)
    if not vector_ok:
        return [dict(item, why="bm25 (вектор недоступен)") for item in text_hits]
    text_norm = _normalize([item["score"] for item in text_hits])
    vector_norm = _normalize([item["score"] for item in vector_hits])
    merged: dict[int, dict] = {}
    text_ids = {hit["id"] for hit in text_hits}
    for hit, norm in zip(vector_hits, vector_norm):
        # При маленьком дневнике KNN возвращает и слабые хвостовые записи.
        # Нулевой vector-only хвост не должен превращать точный hybrid-запрос
        # в выдачу всего дневника; если текста нет, сохраняем весь top-k.
        if text_ids and hit["id"] not in text_ids and norm <= 1e-9:
            continue
        merged[hit["id"]] = {
            "id": hit["id"],
            "score": W_VECTOR * norm,
            "why": f"cos={norm:.2f}",
            "snippet": "",
        }
    for hit, norm in zip(text_hits, text_norm):
        if hit["id"] in merged:
            merged[hit["id"]]["score"] += W_TEXT * norm
            merged[hit["id"]]["why"] += f" + bm25={norm:.2f}"
            merged[hit["id"]]["snippet"] = hit["snippet"]
        else:
            merged[hit["id"]] = {
                "id": hit["id"],
                "score": W_TEXT * norm,
                "why": f"bm25={norm:.2f}",
                "snippet": hit["snippet"],
            }
    ranked = sorted(merged.values(), key=lambda item: item["score"], reverse=True)
    return ranked[:k]
