############################################################
# ライブラリの読み込み
############################################################
import os
import sys
import logging
import tempfile
import unicodedata
from pathlib import Path
from logging.handlers import TimedRotatingFileHandler
from uuid import uuid4

import streamlit as st
import pandas as pd
from dotenv import load_dotenv

from langchain_community.document_loaders.csv_loader import CSVLoader
from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores import Chroma
from langchain_openai import OpenAIEmbeddings
from langchain.retrievers import EnsembleRetriever

import utils
import constants as ct


############################################################
# 設定関連
############################################################
ENV_PATH = Path(__file__).resolve().parent / ".env"
# UTF-8 の .env を、このプロジェクト直下だけ読む
load_dotenv(dotenv_path=ENV_PATH, encoding="utf-8", override=True)

# （モジュール直下では st.* を呼ばない。ログだけ出す）
logging.getLogger(ct.LOGGER_NAME).info(f"DEBUG: Using .env -> {ENV_PATH}")
logging.getLogger(ct.LOGGER_NAME).info(
    f"DEBUG: OPENAI_API_KEY loaded -> {bool(os.getenv('OPENAI_API_KEY'))}"
)


############################################################
# 関数定義
############################################################

def initialize():
    """
    画面読み込み時に実行する初期化処理
    """
    initialize_session_state()
    initialize_session_id()
    initialize_logger()
    initialize_retriever()


def initialize_logger():
    """
    ログ出力の設定
    """
    os.makedirs(ct.LOG_DIR_PATH, exist_ok=True)

    logger = logging.getLogger(ct.LOGGER_NAME)
    if logger.hasHandlers():
        return

    log_handler = TimedRotatingFileHandler(
        os.path.join(ct.LOG_DIR_PATH, ct.LOG_FILE),
        when="D",
        encoding="utf8"
    )
    formatter = logging.Formatter(
        f"[%(levelname)s] %(asctime)s line %(lineno)s, in %(funcName)s, session_id={st.session_state.session_id}: %(message)s"
    )
    log_handler.setFormatter(formatter)
    logger.setLevel(logging.INFO)
    logger.addHandler(log_handler)


def initialize_session_id():
    """
    セッションIDの作成
    """
    if "session_id" not in st.session_state:
        st.session_state.session_id = uuid4().hex


def initialize_session_state():
    """
    初期化データの用意
    """
    if "messages" not in st.session_state:
        st.session_state.messages = []


def initialize_retriever():
    """
    Retrieverを作成（@st.cache_resource対応＋フォールバック機構付き）
    """
    logger = logging.getLogger(ct.LOGGER_NAME)
    if "retriever" in st.session_state:
        return

    # --- CSV 読み込み（文字コードを自動判定 → UTF-8正規化）---
    csv_path = Path(ct.RAG_SOURCE_PATH)
    tried = []
    df = None
    for enc in ("utf-8", "utf-8-sig", "cp932"):
        try:
            df = pd.read_csv(csv_path, encoding=enc, dtype=str)
            break
        except Exception as e:
            tried.append(f"{enc}: {e!s}")

    if df is None:
        logger.error(
            "products.csv を読み込めませんでした。以下のエンコーディングで失敗: " + " / ".join(tried)
        )
        raise RuntimeError("products.csv の文字コードを UTF-8 へ保存し直してください。")

    # ==== ここからキャッシュ化（同一セッション＆リランで再構築を防止）====
    stat = csv_path.stat()
    sig = f"{stat.st_mtime_ns}:{stat.st_size}:{ct.TOP_K}:{tuple(ct.RETRIEVER_WEIGHTS)}:{bool(os.getenv('OPENAI_API_KEY'))}"

    @st.cache_resource(show_spinner=False)
    def _build_retriever(_signature: str):
        # 一時CSVを作ってCSVLoaderで読む
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8", newline="") as tmp:
            tmp_path = Path(tmp.name)
            df.to_csv(tmp_path, index=False, encoding="utf-8")

        try:
            loader = CSVLoader(str(tmp_path), encoding="utf-8")
            docs = loader.load()
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass

        # Windowsの化け対策
        for doc in docs:
            doc.page_content = adjust_string(doc.page_content)
            for key in list(doc.metadata.keys()):
                doc.metadata[key] = adjust_string(doc.metadata[key])

        docs_all = [doc.page_content for doc in docs]

        # --- ベクトル検索（OpenAIEmbeddings + Chroma エフェメラル）
        use_vec = bool(os.getenv("OPENAI_API_KEY"))
        retriever_vec = None
        if use_vec:
            try:
                embeddings = OpenAIEmbeddings()
                db = Chroma.from_documents(docs, embedding=embeddings)
                retriever_vec = db.as_retriever(search_kwargs={"k": ct.TOP_K})
            except Exception as e:
                logger.warning(f"vector retriever disabled: {e}")
                retriever_vec = None
                use_vec = False

        # --- BM25（日本語前処理つき）
        bm25 = BM25Retriever.from_texts(
            docs_all,
            preprocess_func=utils.preprocess_func,
            k=ct.TOP_K
        )

        # --- アンサンブル or 単独BM25 ---
        if use_vec and retriever_vec is not None:
            logger.info("initialize_retriever(): retriever ready (ensemble)")
            return EnsembleRetriever(
                retrievers=[bm25, retriever_vec],
                weights=ct.RETRIEVER_WEIGHTS
            )
        else:
            logger.info("initialize_retriever(): retriever ready (BM25 only)")
            return bm25

    st.session_state.retriever = _build_retriever(sig)
    # ==== ここまでキャッシュ化 ====


def adjust_string(s):
    """
    Windows環境でRAGが正常動作するよう調整
    """
    if type(s) is not str:
        return s
    if sys.platform.startswith("win"):
        s = unicodedata.normalize("NFC", s)
        s = s.encode("cp932", "ignore").decode("cp932")
        return s
    return s
