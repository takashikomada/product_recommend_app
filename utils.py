import re
import random
import unicodedata
from pathlib import Path

import pandas as pd
import streamlit as st
import constants as ct

def build_error_message(message: str) -> str:
    return f"{message}　{ct.COMMON_ERROR_MESSAGE}"

def _normalize_text(text: str) -> str:
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[^\w\sぁ-んァ-ン一-龠ー\.]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def preprocess_func(text: str) -> str:
    return _normalize_text(text)

def _load_products_df() -> pd.DataFrame:
    csv_path = Path(__file__).resolve().parent / "data" / "products.csv"
    last_err = None
    for enc in ("utf-8", "utf-8-sig", "cp932"):
        try:
            return pd.read_csv(csv_path, encoding=enc, dtype=str)
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"products.csv を読み込めませんでした: {last_err!s}")

_STOCK_LOW = {"少", "すく", "わずか", "残りわずか", "わず"}
_STOCK_NONE = {"ない", "無し", "なし", "在庫切れ"}
_POPULAR = {"人気", "レビュー", "評価", "評判", "売れ", "ランキング"}

_CATEGORIES = {
    "イヤホン": ["イヤホン", "ワイヤレス", "ヘッドホン", "ear"],
    "ライト": ["ライト", "照明", "デスクライト", "lamp"],
    "加湿器": ["加湿器", "humid"],
    "枕": ["枕", "ピロー"],
    "時計": ["時計", "ウォッチ"],
}

def _parse_count(prompt: str, default: int = 1, limit: int = 5) -> int:
    m = re.search(r"(\d+)\s*件|\s*(\d+)\s*つ|\s*(\d+)\s*個", prompt)
    n = None
    if m:
        for g in m.groups():
            if g:
                n = int(g)
                break
    if n is None:
        m2 = re.search(r"トップ\s*(\d+)", prompt)
        if m2:
            n = int(m2.group(1))
    if n is None:
        n = default
    return max(1, min(limit, n))

def _intent_from_prompt(prompt: str) -> dict:
    p = _normalize_text(prompt)

    stock = "any"
    if any(w in p for w in _STOCK_NONE):
        stock = "none"
    elif any(w in p for w in _STOCK_LOW):
        stock = "low"

    popular = any(w in p for w in _POPULAR)

    category = ""
    for cat, kws in _CATEGORIES.items():
        if any(_normalize_text(k) in p for k in kws):
            category = cat
            break

    return {"stock": stock, "popular": popular, "category": category}

def _doc_id(doc) -> str:
    try:
        text = getattr(doc, "page_content", "") or ""
        for line in text.splitlines():
            if line.lower().startswith("id:"):
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return ""

def _score_text(text: str, query: str) -> int:
    t = text or ""
    q = query or ""
    score = 0
    for w in ["在庫", "人気", "おすすめ", "イヤホン", "枕", "加湿器", "ライト"]:
        if (w in q) and (w in t):
            score += 2
    for field in ("name:", "category:", "description:", "maker:"):
        if field in t:
            score += 1
    return score

def _safe_retrieve(prompt: str):
    retr = st.session_state.retriever
    if hasattr(retr, "invoke"):
        return retr.invoke(prompt)
    # LangChain古い系
    if hasattr(retr, "get_relevant_documents"):
        return retr.get_relevant_documents(prompt)
    raise RuntimeError("Retriever が無効です（invoke/get_relevant_documents の両方が見つかりません）。")

def search_products(prompt: str):
    want = _parse_count(prompt, default=1, limit=5)

    # Retriever 実行（互換呼び分け）
    docs = _safe_retrieve(prompt)
    if not isinstance(docs, list):
        docs = [docs]

    intent = _intent_from_prompt(prompt)
    df = _load_products_df()

    stock = intent["stock"]
    if stock == "none":
        df = df[df["stock_status"] == ct.STOCK_NONE_TEXT]
    elif stock == "low":
        df = df[df["stock_status"] == ct.STOCK_LOW_TEXT]
    elif stock == "any":
        df = df[df["stock_status"] != ct.STOCK_NONE_TEXT]

    cat = intent["category"]
    if cat and not df.empty:
        mask = (
            df["name"].fillna("").str.contains(cat, case=False)
            | df["category"].fillna("").str.contains(cat, case=False)
            | df["description"].fillna("").str.contains(cat, case=False)
        )
        df = df[mask]

    if intent["popular"] and not df.empty:
        def _to_float(x):
            try: return float(str(x))
            except Exception: return 0.0
        def _to_int(x):
            try: return int(str(x).replace(",", ""))
            except Exception: return 0
        df["_score_num"] = df["score"].map(_to_float)
        df["_review_num"] = df["review_number"].map(_to_int)
        df = df.sort_values(by=["_score_num", "_review_num"], ascending=False)

    id_candidates = [str(x) for x in df["id"].tolist()[: max(want, 1) * 5]] if not df.empty else []

    picked = []
    id_to_doc = {}
    for d in docs:
        did = _doc_id(d)
        if did:
            id_to_doc.setdefault(did, d)
    for did in id_candidates:
        if did in id_to_doc and id_to_doc[did] not in picked:
            picked.append(id_to_doc[did])

    if len(picked) < want:
        remain = [d for d in docs if d not in picked]
        remain.sort(key=lambda d: _score_text(getattr(d, "page_content", ""), prompt), reverse=True)
        for d in remain:
            picked.append(d)
            if len(picked) >= want:
                break

    if len(picked) > want:
        picked = random.sample(picked[: max(want * 3, want)], k=want)

    return picked[:want]

