"""
Buddy — онбординг-агент. Streamlit-интерфейс для тестирования.
Запуск: streamlit run streamlit_app.py
"""
import os

import streamlit as st

st.set_page_config(
    page_title="Buddy — онбординг-агент",
    page_icon="🤖",
    layout="centered",
)

# Инициализация при первом запуске
try:
    from app.streamlit_chat import StreamlitChatService
    from app.onboarding import extract_role_from_message, get_display_role, ROLE_DISPLAY

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
st.caption(
    "Задавай вопросы о компании, отпуске, доступах, процессах. "
    "Я ищу релевантное в базе и формирую ответ через GPT (если настроен ключ OpenRouter)."
)
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


CIRCLE_ALIASES = {
    "маркет": "маркетинг",
    "marketing": "маркетинг",
    "sales": "sales",
    "продаж": "sales",
    "product": "product",
    "продукт": "product",
    "docs": "docs",
    "legal": "legal",
    "new business": "new business",
    "nb": "new business",
    "projects": "projects",
    "инфра": "инфраструктура и ит",
    "it": "инфраструктура и ит",
    "hr": "hr",
    "client care": "client care",
}


def _extract_circle(text: str) -> str | None:
    t = (text or "").lower()
    for alias, normalized in CIRCLE_ALIASES.items():
        if alias in t:
            return normalized
    return None


def _extract_known_role(text: str) -> str | None:
    role = extract_role_from_message(text or "")
    if role in ROLE_DISPLAY:
        return role
    return None


def _starter_plan(role: str, circle: str) -> str:
    role_text = get_display_role(role)
    return (
        f"Отлично, вижу тебя как **{role_text}** в круге **{circle}** 🙌\n\n"
        "Я помогу тебе с адаптацией. Давай начнем с простого плана на сегодня:\n\n"
        "1. Установи и настрой **MChat (Mattermost)**, чтобы не пропустить важные сообщения.\n"
        "2. Подпишись на каналы: `news`, `talk`, `benefits`, `okr`, `правократия`, `pravo_job`.\n"
        "3. Проверь доступы к ключевым сервисам: **E1**, **HR**, **FOKUS**, **почта**.\n"
        "4. Напиши приветственный пост в `talk`.\n"
        "5. Если где-то нет доступа — сразу скажи, я подскажу, куда завести заявку.\n\n"
        "Если хочешь, могу сейчас дать план именно под твою роль на первую неделю."
    )


# Инициализация истории чата
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": (
                "Привет! Я Buddy — помогу тебе с адаптацией в компании 👋\n\n"
                "Для начала напиши, пожалуйста, **твою роль** и **круг**.\n"
                "Например: «Я backend, круг Product»."
            ),
        }
    ]

if "profile" not in st.session_state:
    st.session_state.profile = {
        "role": None,
        "circle": None,
        "onboarding_done": False,
    }

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
                profile = st.session_state.profile

                # Мини-онбординг: сначала узнаем роль + круг
                if not profile["onboarding_done"]:
                    role = profile["role"] or _extract_known_role(prompt)
                    circle = profile["circle"] or _extract_circle(prompt)
                    profile["role"] = role
                    profile["circle"] = circle

                    if not role and not circle:
                        response = (
                            "Хочу лучше тебе помочь с адаптацией. Напиши, пожалуйста, "
                            "**роль** и **круг**. Например: «Я маркетолог, круг Marketing»."
                        )
                    elif role and not circle:
                        response = (
                            f"Супер, роль поняла: **{get_display_role(role)}**. "
                            "Теперь подскажи, в каком ты круге? Например: Product, Marketing, Sales, Legal."
                        )
                    elif circle and not role:
                        response = (
                            f"Отлично, круг: **{circle}**. "
                            "Теперь напиши, пожалуйста, твою роль (например: backend, маркетолог, менеджер)."
                        )
                    else:
                        profile["onboarding_done"] = True
                        response = _starter_plan(role, circle)
                else:
                    response = service.answer(
                        prompt,
                        user_role=profile.get("role"),
                        user_circle=profile.get("circle"),
                    )

                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
            except Exception as e:
                err_msg = f"Ошибка: {e}"
                st.error(err_msg)
                st.session_state.messages.append({"role": "assistant", "content": err_msg})
