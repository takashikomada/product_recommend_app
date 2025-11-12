"""
このファイルは、Webアプリのメイン処理が記述されたファイルです。
"""
import constants as ct
import streamlit as st

st.set_page_config(page_title=ct.APP_NAME, page_icon="🛒", layout="wide")

from initialize import initialize
import components as cn
import utils
import logging

try:
    initialize()
except Exception as e:
    import traceback
    st.error("初期化処理でエラーが発生しました。詳細ログを表示します。")
    st.code("".join(traceback.format_exception(type(e), e, e.__traceback__)))
    st.stop()

logger = logging.getLogger(ct.LOGGER_NAME)

if "initialized" not in st.session_state:
    st.session_state.initialized = True
    logger.info(ct.APP_BOOT_MESSAGE)

cn.display_app_title()

if not st.session_state.get("messages"):
    cn.display_initial_ai_message()
    st.session_state.messages = []

try:
    cn.display_conversation_log()
except Exception as e:
    logger.error(f"{ct.CONVERSATION_LOG_ERROR_MESSAGE}\n{e}")
    st.error(utils.build_error_message(ct.CONVERSATION_LOG_ERROR_MESSAGE))
    st.stop()

chat_message = st.chat_input(ct.CHAT_INPUT_HELPER_TEXT)

if chat_message:
    logger.info({"message": chat_message})
    with st.chat_message("user", avatar=ct.USER_ICON_FILE_PATH):
        st.markdown(chat_message)

    with st.chat_message("assistant", avatar=ct.AI_ICON_FILE_PATH):
        with st.spinner(ct.SPINNER_TEXT):
            try:
                # ★ N件対応の検索
                results = utils.search_products(chat_message)
            except Exception as e:
                logger.error(f"{ct.RECOMMEND_ERROR_MESSAGE}\n{e}")
                st.error(utils.build_error_message(ct.RECOMMEND_ERROR_MESSAGE))
                st.stop()
                raise

            # ★ N件を個別カードで表示（互換のため [doc] で渡す）
            for doc in results:
                cn.display_product([doc])

            logger.info({"message": results})

    st.session_state.messages.append({"role": "user", "content": chat_message})
    st.session_state.messages.append({"role": "assistant", "content": results})
