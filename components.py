"""
このファイルは、画面表示に特化した関数定義のファイルです。
"""
import logging
import streamlit as st
import constants as ct
import pandas as pd
from pathlib import Path
import os
from glob import glob

logger = logging.getLogger("app_logger")

@st.cache_data(show_spinner=False)
def _load_products_csv() -> pd.DataFrame:
    csv_path = Path(__file__).resolve().parent / "data" / "products.csv"
    return pd.read_csv(csv_path, dtype=str, encoding="utf-8")

def display_app_title():
    st.markdown(f"## {ct.APP_NAME}")


def display_initial_ai_message():
    with st.chat_message("assistant", avatar=ct.AI_ICON_FILE_PATH):
        st.markdown("こちらは対話型の商品レコメンド生成AIアプリです。「こんな商品が欲しい」という情報・要望を画面下部のチャット欄から送信いただければ、おすすめの商品をレコメンドいたします。")
        st.markdown("**入力例**")
        st.info("""
        - 「長時間使える、高音質なワイヤレスイヤホン」
        - 「机のライト」
        - 「USBで充電できる加湿器」
        """)


def display_conversation_log():
    for message in st.session_state.messages:
        if message["role"] == "user":
            with st.chat_message("user", avatar=ct.USER_ICON_FILE_PATH):
                st.markdown(message["content"])
        else:
            with st.chat_message("assistant", avatar=ct.AI_ICON_FILE_PATH):
                display_product(message["content"])


def display_product(result):
    """
    商品カードの描画
    Args:
        result: [doc] 形式（互換のため1件ずつ渡す）
    """
    logger = logging.getLogger("app_logger")

    st.markdown("以下の商品をご提案いたします。")

    lines = result[0].page_content.split("\n")
    product = {}
    for ln in lines:
        if ":" in ln:
            k, v = ln.split(":", 1)
            product[k.strip()] = v.strip()

    # ① 見出し
    st.success(f"商品名：{product.get('name','')}（商品ID: {product.get('id','')}）\n\n価格：{product.get('price','')}")

    # ② 在庫バナー
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
        st.warning(f"{ct.WARNING_ICON} ご好評につき、在庫数が{ct.STOCK_LOW_TEXT}です。購入をご希望の場合、お早めのご注文をおすすめいたします。")
    elif stock == ct.STOCK_NONE_TEXT:
        st.error(f"{ct.OUTOFSTOCK_ICON} 申し訳ございませんが、本商品は在庫切れとなっております。入荷までしばらくお待ちください。")

    # ③ 属性情報
    st.code(
        f"商品カテゴリ：{product.get('category','')}\n\nメーカー：{product.get('maker','')}\n\n評価：{product.get('score','')}({product.get('review_number','')}件)",
        language=None,
        wrap_lines=True,
    )

    # ④ 画像処理（CSVの file_name をIDで引き、複数フォルダ・拡張子・ゆるい一致で探索）
    file_name = ""
try:
    df = _load_products_csv()
    row = df[df["id"].astype(str) == str(product.get("id", ""))]
    if not row.empty and "file_name" in row.columns:
        file_name = str(row.iloc[0]["file_name"]).strip()
except Exception as e:
    logger.warning(f"image lookup skipped: {e}")

    # 探索ルートを複数用意（教材ごとに配置が違っても拾えるように）
    roots = [
        Path(__file__).resolve().parent / "images" / "products",
        Path(__file__).resolve().parent / "image" / "products",
        Path(__file__).resolve().parent / "assets" / "images" / "products",
        Path(__file__).resolve().parent / "static" / "images" / "products",
        Path(__file__).resolve().parent / "images",  # 直下に置いてある場合
    ]

    # 拡張子候補
    exts = [".png", ".jpg", ".jpeg", ".webp"]

    def _find_image_by_candidates(_roots, _stem_or_name):
        """厳密一致→拡張子差替え→ゆるい（stem一致・部分一致・大文字小文字無視）"""
        # 入力が "a/b/c.png" 的なら stem と name を分離
        _name = Path(_stem_or_name).name
        _stem = Path(_stem_or_name).stem

        # 1) 厳密一致
        for r in _roots:
            p = r / _name
            try:
                if p.is_file():
                    return p
            except Exception:
                pass

        # 2) 拡張子置換
        for r in _roots:
            for ext in exts:
                p = r / f"{_stem}{ext}"
                try:
                    if p.is_file():
                        return p
                except Exception:
                    pass

        # 3) ゆるい一致（stem一致・部分一致・大小無視）
        for r in _roots:
            try:
                for p in r.glob("*"):
                    nm = p.name
                    if p.is_file():
                        # stem 完全一致
                        if Path(nm).stem.lower() == _stem.lower():
                            return p
                        # 部分一致（"earphone" in "earphone_black.jpg" など）
                        if _stem.lower() and (_stem.lower() in nm.lower()):
                            return p
            except Exception:
                pass

        return None

    # 候補名を決定（CSVの file_name が無い場合は id ベース）
    candidates_to_try = []
    if file_name:
        candidates_to_try.append(file_name)
    else:
        # CSVに file_name が無ければ id.拡張子 を当てにいく
        id_stem = str(product.get("id", "")).strip()
        if id_stem:
            candidates_to_try.append(id_stem)

    chosen_path = None
    for nm in candidates_to_try:
        chosen_path = _find_image_by_candidates(roots, nm)
        if chosen_path:
            break

    if chosen_path:
        st.image(str(chosen_path), width=400)
        logger.debug(f"image resolved -> {chosen_path}")
    else:
        # デバッグ情報を画面にも軽く表示（ユーザーにも見える形で）
        st.info("画像ファイルが見つかりませんでした。")
        # ログには探索状況をまとめて出す
        try:
            existing_samples = []
            for r in roots:
                if r.exists():
                    names = sorted([p.name for p in r.glob("*") if p.is_file()])[:30]
                    existing_samples.append(f"{r} -> {names}")
                else:
                    existing_samples.append(f"{r} -> (not exists)")
            logger.warning(
                "image not found | "
                f"id={product.get('id','')} file_name='{file_name}' | "
                f"roots={ [str(r) for r in roots] } | "
                f"samples={existing_samples}"
            )
        except Exception:
            pass
        
    # ⑤ 説明
    desc = product.get("description", "")
    if desc:
        st.code(desc, language=None, wrap_lines=True)

    # ⑥ おすすめ対象ユーザー
    rec = product.get("recommended_people", "")
    if rec:
        st.markdown("**こんな方におすすめ！**")
        st.info(rec)

    # ⑦ 商品ページリンク
    st.link_button("商品ページを開く", type="primary", use_container_width=True, url="https://google.com")
