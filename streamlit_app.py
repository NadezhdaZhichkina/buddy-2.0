"""
Buddy — онбординг-агент. Streamlit-интерфейс для тестирования.
Запуск: streamlit run streamlit_app.py
"""
import streamlit as st
import os

st.set_page_config(
    page_title="Buddy — онбординг-агент",
    page_icon="🤖",
    layout="centered",
)

# Инициализация при первом запуске
try:
    from app.streamlit_chat import StreamlitChatService

    def _get_secret(name: str, default: str = "") -> str:
        try:
            return str(st.secrets.get(name, default))
        except Exception:
            return default

    def _get_openrouter_api_key() -> str:
        # Поддерживаем разные названия ключа в Secrets
        variants = [
            "OPENROUTER_API_KEY",
            "openrouter_api_key",
            "OPEN_ROUTER_API_KEY",
        ]
        for k in variants:
            v = _get_secret(k, "").strip()
            if v:
                return v
        # fallback для локального запуска
        return os.getenv("OPENROUTER_API_KEY", "").strip()

    def _get_openrouter_model() -> str:
        variants = [
            "OPENROUTER_MODEL",
            "openrouter_model",
        ]
        for k in variants:
            v = _get_secret(k, "").strip()
            if v:
                return v
        return os.getenv("OPENROUTER_MODEL", "openai/gpt-4.1-mini").strip()

    resolved_key = _get_openrouter_api_key()
    resolved_model = _get_openrouter_model()

    service = StreamlitChatService(
        openrouter_api_key=resolved_key,
        openrouter_model=resolved_model,
    )
except Exception as e:
    st.error(f"Ошибка инициализации: {e}")
    st.stop()

st.title("🤖 Buddy — онбординг-агент")
st.caption("Задавай вопросы о компании, отпуске, доступах, процессах. Я ищу релевантное в базе и формирую ответ через GPT (если настроен ключ OpenRouter).")
if service.llm_enabled:
    st.success(f"LLM: включен (OpenRouter, model: {resolved_model})")
else:
    st.info("LLM: выключен — ответы только по базе знаний. Добавь OPENROUTER_API_KEY в Secrets Streamlit Cloud.")

with st.expander("Диагностика LLM", expanded=False):
    st.write(
        {
            "llm_enabled": service.llm_enabled,
            "model": resolved_model,
            "key_detected": bool(resolved_key),
            "key_prefix": (resolved_key[:8] + "...") if resolved_key else "",
        }
    )

# Инициализация истории чата
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Привет! Я Buddy — ИИ-помощник по онбордингу. Задавай любой вопрос: о компании, отпуске, доступах, процессах."}
    ]

# Показываем историю
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Поле ввода
if prompt := st.chat_input("Напиши вопрос…"):
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Думаю…"):
            try:
                response = service.answer(prompt)
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
            except Exception as e:
                err_msg = f"Ошибка: {e}"
                st.error(err_msg)
                st.session_state.messages.append({"role": "assistant", "content": err_msg})
