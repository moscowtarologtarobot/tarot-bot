# Самый простой запуск с iPhone

1. Создай бота в BotFather и получи токен.
2. Получи OpenAI API key.
3. Создай GitHub-репозиторий и загрузи все файлы из этой папки.
4. Зайди в Railway с iPhone.
5. New Project -> Deploy from GitHub Repo -> выбери репозиторий.
6. В Variables добавь:
   - TELEGRAM_BOT_TOKEN
   - OPENAI_API_KEY
   - OPENAI_MODEL=gpt-5-mini
   - PRICE_XTR=150
7. Deploy.
8. Открой бота в Telegram и отправь /start.

В этом архиве уже есть Procfile и railway.json, так что Railway запустит бота как worker без дополнительных настроек.
