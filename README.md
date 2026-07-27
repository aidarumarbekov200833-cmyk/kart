# AutoFlow Unified

Платформа автоматизации лидогенерации: парсинг контактов из YouTube, верификация Telegram и авторассылка.

## Стек

- **Backend:** Flask 3, Telethon, SQLite
- **Frontend:** Jinja2 + Tailwind (CDN), собственная дизайн-система (13 тем, glassmorphism)
- **Infra:** Docker Compose, Gunicorn, Nginx

## Быстрый старт

```bash
cp .env.example .env
# сгенерируйте ключ: openssl rand -hex 32 -> SECRET_KEY
# заполните TELEGRAM_* и PUBLIC_BASE_URL
docker compose up -d --build
```

Приложение будет доступно на `http://localhost:8000`.

## Конфигурация (`.env`)

| Переменная | Описание |
|-----------|----------|
| `SECRET_KEY` | Ключ сессий Flask (обязательно) |
| `DEV_MODE` | `False` в проде (включает Secure cookies) |
| `PUBLIC_BASE_URL` | Публичный URL для Telegram callback |
| `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` | С my.telegram.org |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_BOT_USERNAME` | Для Login Widget |
| `ADMIN_TELEGRAM_USERNAME` / `ADMIN_TELEGRAM_ID` | Админ |
| `MAX_TG_ACCOUNTS` | Лимит TG-аккаунтов на пользователя |

## Безопасность

- Проверка Telegram Login через HMAC (spec-compliant, `hmac.compare_digest`)
- CSRF-защита (Flask-WTF) для всех POST/PUT/PATCH/DELETE
- Secure/HttpOnly/SameSite cookies
- Rate limiting (Flask-Limiter)
- Заголовки безопасности (CSP, HSTS, X-Frame-Options) на nginx + Flask
- Валидация ввода (телефон, ключевые слова)

## Страницы

- `/` — лендинг (гость) / редирект на dashboard (авторизован)
- `/login` — вход через Telegram
- `/dashboard` — панель пользователя
- `/admin` — админ-панель
- `/terms` — условия использования

## Добавление Telegram-аккаунта

```bash
python auth_telegram.py
```
