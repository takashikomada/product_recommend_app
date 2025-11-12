############################################################
# 画面表示以外の関数定義（Cloud対応版：sudachipyが無くても動く）
############################################################
import logging
import re
import random
import unicodedata
from pathlib import Path

import pandas as pd
import streamlit as st
import constants as ct

############################################################
# sudachipy があれば使い、無ければ軽量フォールバック
############################################################
try:
    from sudachipy import tokenizer as _tok, dictionary as _dict  # optional
    _sudachi_tokenizer = _dict.Dictionary().create()
    _SPLIT = _tok.Tokenizer.SplitMode.C

    def _tokenize_ja(text: str):
        if not isinstance(text, str):
            return []
        return [m.surface().lower() for m in _sudachi_tokenizer.tokenize(text, _SPLIT)]
except Exception:
    # Streamlit Cloud などで sudachipy が無い場合はこちらを使う
    def _tokenize_ja(text: str):
        if not isinstance(text, str):
            return []
        s = unicodedata.normalize("NFKC", text).lower()
        # 英数字・ひらがな・カタカナ・漢字以外は空白に
        s = re.sub(r"[^\wぁ-んァ-ヶ一-龥ー]", " ", s)
        s = s.replace("_", " ")
        return [t for t in s.split() if t]

############################################################
# BM25 用の前処理（日本語トークナイズ）
############################################################
def preprocess_func(text: str):
    return _tokenize_ja(text)

############################################################
# 共通：エラーメッセージ連結
############################################################
def build_error_message(message: str) -> str:
    return "\n".join([message, ct.COMMON_ERROR_MESSAGE])

