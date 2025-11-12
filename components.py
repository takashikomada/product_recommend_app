"""
画面表示に特化した関数定義
"""
import logging
from pathlib import Path

import pandas as pd
import streamlit as st

import constants as ct

logger = logging.getLogger("app_logger")

@st.cache_data(show_spinner=False)
def _load_products_csv() -> pd.DataFrame:
    csv_path = Path(__file__).resolve().parent / "data" / "products.csv"
    return pd.read_csv(csv_path, dtype=str, encoding="utf-8")

def display_app_title():
    st.markdown(f"## {ct.APP_NAME}")

def display_initial_ai_message():
    with st.chat_message("assistant", avatar=ct.AI_ICON_FILE_PATH):
        st.markdown(
            "こちらは対話型の商品レコメンド生成AIアプリです。「こんな商品が欲しい」という情報・要望を画面下部のチャット欄から送信いただければ、おすすめの商品をレコメンドいたします。"
        )
        st.markdown("**入力例**")
        st.info(
            """
        - 「長時間使える、高音質なワイヤレスイヤホン」
        - 「机のライト」
        - 「USBで充電できる加湿器」
        """
        )

def display_conversation_log():
    for message in st.session_state.messages:
        if message["role"] == "user":
            with st.chat_message("user", avatar=ct.USER_ICON_FILE_PATH):
                st.markdown(message["content"])
        else:
            with st.chat_message("assistant", avatar=ct.AI_ICON_FILE_PATH):
                display_product(message["content"])

def display_product(result):
    """1件分の商品カードを描画（互換のため [doc] を受け取る）"""
    logger = logging.getLogger("app_logger")
    st.markdown("以下の商品をご提案いたします。")

    # --- 文書→辞書
    lines = result[0].page_content.split("\n")
    product = {}
    for ln in lines:
        if ":" in ln:
            k, v = ln.split(":", 1)
            product[k.strip()] = v.strip()

    # ① 見出し
    st.success(
        f"商品名：{product.get('name','')}（商品ID: {product.get('id','')}）\n\n価格：{product.get('price','')}"
    )

    # ② 在庫バナー（CSV補完あり）
    stock = (product.get("stock_status") or "").strip()
    if not stock:
        try:
            df = _load_products_csv()
            row = df[df["id"].astype(str) == str(product.get("id", ""))]
            if not row.empty and "stock_status" in row.columns:
                stock = (row.iloc[0]["stock_status"] or "").strip()
        except Exception as e:
            logger.warning(f"stock_status lookup skipped: {e}")

    if stock == ct.STOCK_LOW_TEXT:
        st.warning(
            f"{ct.WARNING_ICON} ご好評につき、在庫数が{ct.STOCK_LOW_TEXT}です。購入をご希望の場合、お早めのご注文をおすすめいたします。"
        )
    elif stock == ct.STOCK_NONE_TEXT:
        st.error(
            f"{ct.OUTOFSTOCK_ICON} 申し訳ございませんが、本商品は在庫切れとなっております。入荷までしばらくお待ちください。"
        )

    # ③ 属性情報
    st.code(
        f"商品カテゴリ：{product.get('category','')}\n\nメーカー：{product.get('maker','')}\n\n評価：{product.get('score','')}({product.get('review_number','')}件)",
        language=None,
        wrap_lines=True,
    )

    # ④ 画像表示（CSVの file_name → 複数パス探索）
    file_name = ""
    try:
        df = _load_products_csv()
        row = df[df["id"].astype(str) == str(product.get("id", ""))]
        if not row.empty and "file_name" in row.columns:
            file_name = str(row.iloc[0]["file_name"]).strip()
    except Exception as e:
        logger.warning(f"image lookup skipped: {e}")

    roots = [
        Path(__file__).resolve().parent / "images" / "products",
        Path(__file__).resolve().parent / "image" / "products",
        Path(__file__).resolve().parent / "assets" / "images" / "products",
        Path(__file__).resolve().parent / "static" / "images" / "products",
        Path(__file__).resolve().parent / "images",
    ]
    exts = [".png", ".jpg", ".jpeg", ".webp"]

    def _find_image(stem_or_name: str):
        name = Path(stem_or_name).name
        stem = Path(stem_or_name).stem

        # 厳密一致
        for r in roots:
            p = r / name
            if p.is_file():
                return p
        # 拡張子置換
        for r in roots:
            for ext in exts:
                p = r / f"{stem}{ext}"
                if p.is_file():
                    return p
        # ゆるい一致（stem一致・部分一致・大小無視）
        for r in roots:
            if not r.exists():
                continue
            for p in r.glob("*"):
                if not p.is_file():
                    continue
                nm = p.name
                if Path(nm).stem.lower() == stem.lower():
                    return p
                if stem.lower() and (stem.lower() in nm.lower()):
                    return p
        return None

    candidates = []
    if file_name:
        candidates.append(file_name)
    else:
        pid = str(product.get("id", "")).strip()
        if pid:
            candidates.append(pid)

    chosen = None
    for nm in candidates:
        chosen = _find_image(nm)
        if chosen:
            break

    if chosen:
        st.image(str(chosen), width=400)
    else:
        st.info("画像ファイルが見つかりませんでした。")

