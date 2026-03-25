# Психологический Tarot Bot для Telegram

Готовый Telegram-бот с оплатой за цифровой расклад в Telegram Stars и генерацией разборов через OpenAI Responses API.

## Что умеет
- 1 бесплатная карта для прогрева
- платный психологический расклад из 3 карт
- оплата в Telegram Stars
- хранение пользователей, оплат и раскладов в SQLite
- команда поддержки по оплатам `/paysupport`
- админская статистика `/stats`

## Требования
- Python 3.11+
- Telegram-бот
- OpenAI API key

## Важно про оплату
Для цифровых товаров и услуг Telegram требует использовать **Telegram Stars (`XTR`)**. В этом проекте платный расклад считается цифровой услугой, поэтому invoice создаётся в `XTR`, а `provider_token` остаётся пустым.

## Запуск
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# заполни .env
python bot.py
```

## Настройка
Открой `.env` и укажи:
- `TELEGRAM_BOT_TOKEN`
- `OPENAI_API_KEY`
- `OPENAI_MODEL` — например `gpt-5-mini`
- `PRICE_XTR` — цена расклада в Telegram Stars
- `ADMIN_USER_ID` — необязательно, для команды `/stats`

## Как пользоваться
1. Напиши боту `/start`
2. Отправь вопрос обычным сообщением
3. Нажми кнопку покупки или введи `/buy`
4. Оплати расклад звёздами
5. Бот дождётся `successful_payment` и пришлёт разбор

## Команды
- `/start`
- `/help`
- `/free`
- `/buy`
- `/my`
- `/paysupport`
- `/stats` (только админ)

## Идеи для следующей версии
- несколько видов раскладов
- реферальная система
- промокоды
- авторассылка лучших раскладов в канал
- админ-панель на FastAPI
