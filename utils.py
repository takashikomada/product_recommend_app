############################################################
# 画面表示以外の様々な関数定義のファイルです（拡張版）
############################################################
import logging
import re
import random
from pathlib import Path

import pandas as pd
import streamlit as st
from sudachipy import tokenizer, dictionary  # 既存の前処理で使用
import constants as ct


############################################################
# 既存：エラーメッセージ連結
############################################################
def build_error_message(message):
    return "\n".join([message, ct.COMMON_ERROR_MESSAGE])


############################################################
# 既存：BM25用の日本語前処理
############################################################
def preprocess_func(text):
    logger = logging.getLogger(ct.LOGGER_NAME)
    tokenizer_obj = dictionary.Dictionary(dict="full").create()
    mode = tokenizer.Tokenizer.SplitMode.A
    tokens = tokenizer_obj.tokenize(text, mode)
    words = [token.surface() for token in tokens]
    words = list(set(words))
    return words


############################################################
# 追加：CSVを安全に読む（UTF-8/UTF-8-SIG/CP932）
############################################################
def _load_products_df():
    csv_path = Path(__file__).resolve().parent / "data" / "products.csv"
    for enc in ("utf-8", "utf-8-sig", "cp932"):
        try:
            return pd.read_csv(csv_path, encoding=enc, dtype=str)
        except Exception:
            continue
    raise RuntimeError("products.csv を読み込めませんでした（文字コードをご確認ください）")


############################################################
# 追加：数量抽出（3つ／三つ／3個／複数…）
############################################################
_NUM_PAT = re.compile(r"(\d+)\s*(つ|個|件)?")
_KANJI_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

def _parse_count(prompt: str, default: int = 1, limit: int = 5) -> int:
    p = (prompt or "").strip()
    m = _NUM_PAT.search(p)
    if m:
        n = int(m.group(1))
        return max(1, min(n, limit))
    for k, v in _KANJI_NUM.items():
        if k in p:
            return max(1, min(v, limit))
    if any(w in p for w in ["複数", "いくつか", "数件", "数個"]):
        return 2
    return default


############################################################
# 追加：クエリ意図の抽出（在庫/人気/カテゴリ）
############################################################
def _intent_from_prompt(prompt: str):
    q = prompt or ""
    intent = {"stock": None, "popular": False, "category": None}

    # 在庫
    if ("在庫がない" in q) or ("在庫なし" in q) or ("売り切れ" in q):
        intent["stock"] = "none"
    elif ("在庫が少ない" in q) or ("残りわずか" in q):
        intent["stock"] = "low"
    elif ("在庫がある" in q) or ("在庫あり" in q):
        intent["stock"] = "any"

    # 人気
    if ("人気" in q) or ("評判" in q) or ("レビュー" in q) or ("評価" in q):
        intent["popular"] = True

    # カテゴリ（簡易）
    if any(k in q for k in ["イヤホン", "ヘッドホン", "ワイヤレス", "Bluetooth"]):
        intent["category"] = "イヤホン"
    elif any(k in q for k in ["枕", "ピロー"]):
        intent["category"] = "枕"
    elif "加湿器" in q:
        intent["category"] = "加湿器"
    elif any(k in q for k in ["ライト", "照明", "デスクライト"]):
        intent["category"] = "ライト"

    return intent


############################################################
# 追加：Retriever Doc → id を取り出す（"id: XXX" 前提）
############################################################
def _doc_id(doc) -> str:
    try:
        text = getattr(doc, "page_content", "")
        for line in text.splitlines():
            if line.lower().startswith("id:"):
                return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return ""


############################################################
# 追加：保険用の簡易テキストスコア
############################################################
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


############################################################
# 本体：意図に沿って再フィルタ＆再ランク → N件返す
############################################################
def search_products(prompt: str):
    want = _parse_count(prompt, default=1, limit=5)
    docs = st.session_state.retriever.invoke(prompt)
    if not isinstance(docs, list):
        docs = [docs]

    intent = _intent_from_prompt(prompt)
    df = _load_products_df()

    # 在庫
    stock = intent["stock"]
    if stock == "none":
        df = df[df["stock_status"] == ct.STOCK_NONE_TEXT]      # "なし"
    elif stock == "low":
        df = df[df["stock_status"] == ct.STOCK_LOW_TEXT]       # "残りわずか"
    elif stock == "any":
        df = df[df["stock_status"] != ct.STOCK_NONE_TEXT]      # あり/残りわずか

    # カテゴリ
    cat = intent["category"]
    if cat and not df.empty:
        mask = (
            df["name"].fillna("").str.contains(cat, case=False)
            | df["category"].fillna("").str.contains(cat, case=False)
            | df["description"].fillna("").str.contains(cat, case=False)
        )
        df = df[mask]

    # 人気順（score / review_number）
    if intent["popular"] and not df.empty:
        def _to_float(x):
            try: return float(str(x))
            except: return 0.0
        def _to_int(x):
            try: return int(str(x).replace(",", ""))
            except: return 0
        df["_score_num"] = df["score"].map(_to_float)
        df["_review_num"] = df["review_number"].map(_to_int)
        df = df.sort_values(by=["_score_num", "_review_num"], ascending=False)

    # CSVの優先順から id 候補（多めに）
    id_candidates = [str(x) for x in df["id"].tolist()[: max(want, 1) * 5]] if not df.empty else []

    # Retriever 結果を id 一致で優先採用
    picked = []
    id_to_doc = {}
    for d in docs:
        did = _doc_id(d)
        if did:
            id_to_doc.setdefault(did, d)

    for did in id_candidates:
        if did in id_to_doc and id_to_doc[did] not in picked:
            picked.append(id_to_doc[did])
            if len(picked) >= want:
                break

    # 足りなければスコアで補完
    if len(picked) < want:
        remain = [d for d in docs if d not in picked]
        scored = sorted(remain, key=lambda d: _score_text(getattr(d, "page_content", ""), prompt), reverse=True)
        for d in scored:
            picked.append(d)
            if len(picked) >= want:
                break

    # 0件なら先頭を返す保険
    if not picked and docs:
        picked = docs[:want]

    return picked[:want]
