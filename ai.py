"""Lightweight LLM connector for the in-app AI helper.

Strategy:
- If AI_API_KEY is configured, call an OpenAI-compatible chat completions API
  (Groq by default — free & fast; also works with OpenRouter / OpenAI / others).
- If no key is set OR the call fails, fall back to the built-in keyword answers.

This keeps the helper free and functional out of the box, while allowing a real
LLM to be plugged in via environment variables.
"""
import json
import urllib.request
import urllib.error

from config import settings
from content import AI_ANSWERS, AI_FALLBACK

SYSTEM_PROMPT = (
    "Ты — встроенный помощник сервиса AutoFlow для лидогенерации: парсинг контактов из YouTube, "
    "верификация Telegram и авторассылка. Отвечай кратко, по-русски и по делу. "
    "Напоминай о соблюдении лимитов Telegram и запрете спама. Если вопрос вне темы — вежливо перенаправь."
)


def _keyword_answer(question: str) -> str:
    q = (question or "").strip().lower()
    for k, v in AI_ANSWERS.items():
        if k in q:
            return v
    return ""


def _call_llm(question: str) -> str:
    """Call an OpenAI-compatible chat completions endpoint. Returns '' on failure."""
    if not settings.AI_API_KEY:
        return ""
    payload = {
        "model": settings.AI_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question[:2000]},
        ],
        "temperature": 0.4,
        "max_tokens": 400,
    }
    req = urllib.request.Request(
        settings.AI_API_BASE.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.AI_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8"))
        return (data["choices"][0]["message"]["content"] or "").strip()
    except (urllib.error.URLError, KeyError, IndexError, ValueError, TimeoutError):
        return ""


def answer(question: str) -> dict:
    """Return {'answer': str, 'source': 'llm'|'builtin'} for a user question."""
    admin = settings.ADMIN_TELEGRAM_USERNAME

    llm_reply = _call_llm(question)
    if llm_reply:
        return {"answer": llm_reply, "source": "llm"}

    kw = _keyword_answer(question)
    if kw:
        return {"answer": f"{kw} Если остались вопросы, напишите @{admin}.", "source": "builtin"}

    return {"answer": AI_FALLBACK.format(admin=admin), "source": "builtin"}
