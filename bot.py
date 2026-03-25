import asyncio
import html
import logging
import os
import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Tuple

from dotenv import load_dotenv
from openai import OpenAI
from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Update,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "bot.db"
LOG_PATH = BASE_DIR / "bot.log"

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
BOT_USERNAME = os.getenv("BOT_USERNAME", "")
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5-mini")
PRICE_XTR = int(os.getenv("PRICE_XTR", "150"))
FREE_READING_ENABLED = os.getenv("FREE_READING_ENABLED", "true").lower() == "true"
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID", "")

client = OpenAI(api_key=OPENAI_API_KEY)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[logging.FileHandler(LOG_PATH, encoding="utf-8"), logging.StreamHandler()],
)
logger = logging.getLogger("tarot_bot")


CARD_MEANINGS = {
    "Шут": "новый цикл, смелость начать, доверие к пути",
    "Маг": "инициатива, фокус, способность влиять на ситуацию",
    "Верховная Жрица": "интуиция, скрытые мотивы, внутренняя тишина",
    "Императрица": "забота, рост, изобилие, отношения с телом и ресурсами",
    "Император": "структура, границы, ответственность и контроль",
    "Иерофант": "ценности, правила, обучение, влияние окружения",
    "Влюблённые": "выбор, близость, честность с собой",
    "Колесница": "движение, воля, необходимость удерживать направление",
    "Сила": "мягкая устойчивость, саморегуляция, зрелая уверенность",
    "Отшельник": "пауза, самоанализ, поиск смысла",
    "Колесо Фортуны": "перемены, цикличность, шанс, поворот сюжета",
    "Правосудие": "баланс, последствия, объективный взгляд",
    "Повешенный": "задержка, пересмотр, отпускание старого способа действовать",
    "Смерть": "завершение этапа, трансформация, освобождение",
    "Умеренность": "восстановление, постепенность, эмоциональная интеграция",
    "Дьявол": "зависание, привязки, тревожные сценарии, искушение",
    "Башня": "резкое осознание, слом старой конструкции, освобождающий кризис",
    "Звезда": "надежда, мягкое исцеление, вера в перспективу",
    "Луна": "неясность, тревога, проекции, глубинные чувства",
    "Солнце": "ясность, энергия, открытость, живость",
    "Суд": "пробуждение, переоценка, решающий внутренний зов",
    "Мир": "завершённость, интеграция, переход на новый уровень",
}

SPREADS = {
    "basic": {
        "title": "Психологический расклад — 3 карты",
        "description": "Прошлое • Настоящее • Ближайший вектор",
        "positions": ["Прошлое", "Настоящее", "Ближайший вектор"],
        "price_xtr": PRICE_XTR,
    }
}

SYSTEM_PROMPT = """
Ты — психологический таро-аналитик.

Твой стиль:
- спокойный, умный, эмпатичный;
- без мистического пафоса;
- без категоричных предсказаний и без обещаний результата;
- ты интерпретируешь символы карт как способ посмотреть на внутренние процессы человека.

Правила:
1. Не утверждай будущее как факт.
2. Не используй пугающие формулировки.
3. Не давай медицинских, юридических или финансовых советов.
4. Пиши персонально, но бережно.
5. Давай практический вывод в конце.
6. Допустим лёгкий живой тон, но без клоунады.

Структура ответа:
- короткое вступление на 1-2 предложения;
- отдельный блок на каждую карту;
- в конце: "Что с этим делать сейчас" с 2-3 конкретными шагами.
""".strip()


@dataclass
class UserProfile:
    telegram_user_id: int
    username: str | None
    first_name: str | None
    free_reading_used: int


def db_connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            telegram_user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            free_reading_used INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_user_id INTEGER NOT NULL,
            invoice_payload TEXT NOT NULL,
            telegram_payment_charge_id TEXT,
            currency TEXT,
            total_amount INTEGER,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_user_id INTEGER NOT NULL,
            spread_key TEXT NOT NULL,
            question TEXT,
            cards_json TEXT NOT NULL,
            interpretation TEXT NOT NULL,
            is_free INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def upsert_user(user) -> UserProfile:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT telegram_user_id, username, first_name, free_reading_used FROM users WHERE telegram_user_id = ?",
        (user.id,),
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            """
            UPDATE users
            SET username = ?, first_name = ?, updated_at = ?
            WHERE telegram_user_id = ?
            """,
            (user.username, user.first_name, utc_now(), user.id),
        )
        free_used = int(row["free_reading_used"])
    else:
        cur.execute(
            """
            INSERT INTO users (telegram_user_id, username, first_name, free_reading_used, created_at, updated_at)
            VALUES (?, ?, ?, 0, ?, ?)
            """,
            (user.id, user.username, user.first_name, utc_now(), utc_now()),
        )
        free_used = 0
    conn.commit()
    conn.close()
    return UserProfile(
        telegram_user_id=user.id,
        username=user.username,
        first_name=user.first_name,
        free_reading_used=free_used,
    )


def mark_free_reading_used(user_id: int) -> None:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "UPDATE users SET free_reading_used = 1, updated_at = ? WHERE telegram_user_id = ?",
        (utc_now(), user_id),
    )
    conn.commit()
    conn.close()


def save_payment(user_id: int, payload: str, status: str, charge_id: str | None = None, currency: str | None = None, total_amount: int | None = None) -> None:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO payments (telegram_user_id, invoice_payload, telegram_payment_charge_id, currency, total_amount, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, payload, charge_id, currency, total_amount, status, utc_now()),
    )
    conn.commit()
    conn.close()


def save_reading(user_id: int, spread_key: str, question: str, cards: List[str], interpretation: str, is_free: bool) -> None:
    import json

    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO readings (telegram_user_id, spread_key, question, cards_json, interpretation, is_free, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, spread_key, question, json.dumps(cards, ensure_ascii=False), interpretation, int(is_free), utc_now()),
    )
    conn.commit()
    conn.close()


def get_latest_readings(user_id: int, limit: int = 5) -> List[sqlite3.Row]:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM readings WHERE telegram_user_id = ? ORDER BY id DESC LIMIT ?",
        (user_id, limit),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_stats() -> Tuple[int, int, int]:
    conn = db_connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM payments WHERE status = 'paid'")
    payments = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM readings")
    readings = cur.fetchone()[0]
    conn.close()
    return users, payments, readings


def draw_cards(spread_key: str) -> List[str]:
    spread = SPREADS[spread_key]
    return random.sample(list(CARD_MEANINGS.keys()), len(spread["positions"]))


def render_cards(cards: List[str], positions: List[str]) -> str:
    parts = []
    for pos, card in zip(positions, cards):
        parts.append(f"• {pos}: {card} — {CARD_MEANINGS[card]}")
    return "\n".join(parts)


def build_user_name(user) -> str:
    return user.first_name or user.username or "друг"


def generate_interpretation(question: str, spread_key: str, cards: List[str], name: str) -> str:
    spread = SPREADS[spread_key]
    positions = spread["positions"]
    card_lines = render_cards(cards, positions)
    user_question = question.strip() if question.strip() else "Общий запрос без конкретного вопроса."

    prompt = f"""
Имя пользователя: {name}
Формат расклада: {spread['title']}
Вопрос пользователя: {user_question}
Карты:
{card_lines}

Сделай разбор на русском языке.
""".strip()

    response = client.responses.create(
        model=DEFAULT_MODEL,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.9,
    )
    return response.output_text.strip()


async def send_welcome(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    keyboard = [
        [InlineKeyboardButton("🔮 Бесплатная карта", callback_data="free_card")],
        [InlineKeyboardButton("💳 Купить расклад", callback_data="buy_basic")],
        [InlineKeyboardButton("🧾 Мои расклады", callback_data="my_readings")],
    ]
    text = (
        "Привет. Я твой психологический таро-бот.\n\n"
        "Что умею:\n"
        "— даю 1 бесплатную карту для знакомства;\n"
        f"— делаю платный расклад из 3 карт за {PRICE_XTR} ⭐;\n"
        "— пишу бережно, без мистического пафоса и без жёстких предсказаний.\n\n"
        "Можешь прислать вопрос текстом, а потом нажать «Купить расклад».\n"
        "Например: «Что сейчас происходит в отношениях?»"
    )
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    upsert_user(update.effective_user)
    await send_welcome(update.effective_chat.id, context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "/start — главное меню\n"
        "/free — бесплатная карта (1 раз)\n"
        "/buy — купить платный расклад\n"
        "/my — мои последние расклады\n"
        "/paysupport — поддержка по оплате\n\n"
        "Также можешь просто написать свой вопрос обычным сообщением."
    )
    await update.message.reply_text(text)


async def paysupport(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Поддержка по оплате:\n"
        "1) проверь, списались ли ⭐;\n"
        "2) если платёж прошёл, а расклад не пришёл — напиши /my;\n"
        "3) если проблема осталась, свяжись с владельцем бота и приложи время оплаты.\n\n"
        "Бот хранит telegram_payment_charge_id для разборов спорных ситуаций."
    )
    await update.message.reply_text(text)


async def free_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_profile = upsert_user(update.effective_user)
    if not FREE_READING_ENABLED:
        await update.message.reply_text("Бесплатная карта сейчас отключена. Можно сразу перейти к /buy.")
        return
    if user_profile.free_reading_used:
        await update.message.reply_text("Бесплатная карта уже использована. Но платный расклад всё ещё ждёт тебя на /buy 🙂")
        return

    question = " ".join(context.args).strip() if context.args else "Общий запрос"
    card = random.choice(list(CARD_MEANINGS.keys()))
    meaning = CARD_MEANINGS[card]
    text = (
        f"Твоя бесплатная карта: <b>{html.escape(card)}</b>\n\n"
        f"Смысл карты: {html.escape(meaning)}.\n\n"
        f"На твой запрос «{html.escape(question)}» это похоже на тему, где важно не гнать события, а честно посмотреть, что уже созрело внутри. "
        "Используй это как подсказку, а не как приговор.\n\n"
        f"Если хочешь полный разбор из 3 карт — жми /buy."
    )
    mark_free_reading_used(update.effective_user.id)
    save_reading(update.effective_user.id, "basic", question, [card], text, True)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    question = update.message.text.replace("/buy", "", 1).strip() if update.message and update.message.text else ""
    if question:
        context.user_data["pending_question"] = question
    await send_invoice(update.effective_chat.id, context)


async def my_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rows = get_latest_readings(update.effective_user.id)
    if not rows:
        await update.message.reply_text("Пока раскладов нет. Начни с /free или /buy.")
        return
    pieces = ["Твои последние расклады:\n"]
    for row in rows:
        created = row["created_at"].split("T")[0]
        q = row["question"] or "без вопроса"
        pieces.append(f"• #{row['id']} — {created} — {q}")
    pieces.append("\nНапиши /buy, чтобы получить новый расклад.")
    await update.message.reply_text("\n".join(pieces))


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not ADMIN_USER_ID or str(update.effective_user.id) != str(ADMIN_USER_ID):
        await update.message.reply_text("Команда только для админа.")
        return
    users, payments, readings = get_stats()
    await update.message.reply_text(
        f"Статистика:\nПользователи: {users}\nУспешные оплаты: {payments}\nВсего раскладов: {readings}"
    )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return
    upsert_user(update.effective_user)
    text = update.message.text.strip()
    if text.startswith("/"):
        return
    context.user_data["pending_question"] = text
    keyboard = InlineKeyboardMarkup(
        [[InlineKeyboardButton(f"💳 Купить расклад за {PRICE_XTR} ⭐", callback_data="buy_basic")]]
    )
    await update.message.reply_text(
        "Вопрос сохранён. Хороший, кстати.\n\n"
        "Когда будешь готов, нажми кнопку ниже — и я сделаю психологический расклад из 3 карт именно под этот запрос.",
        reply_markup=keyboard,
    )


async def send_invoice(chat_id: int, context: ContextTypes.DEFAULT_TYPE) -> None:
    spread = SPREADS["basic"]
    await context.bot.send_invoice(
        chat_id=chat_id,
        title=spread["title"],
        description=spread["description"],
        payload="spread:basic",
        currency="XTR",
        prices=[LabeledPrice(label=spread["title"], amount=spread["price_xtr"])],
        provider_token="",
        start_parameter="psychotarot-basic",
    )


async def free_card_from_message(message, user) -> None:
    user_profile = upsert_user(user)
    if not FREE_READING_ENABLED:
        await message.reply_text("Бесплатная карта сейчас отключена. Можно сразу перейти к /buy.")
        return
    if user_profile.free_reading_used:
        await message.reply_text("Бесплатная карта уже использована. Но платный расклад всё ещё ждёт тебя на /buy 🙂")
        return

    card = random.choice(list(CARD_MEANINGS.keys()))
    meaning = CARD_MEANINGS[card]
    text = (
        f"Твоя бесплатная карта: <b>{html.escape(card)}</b>\n\n"
        f"Смысл карты: {html.escape(meaning)}.\n\n"
        "Сейчас это похоже на внутренний сюжет, который уже просит честности и внимания. "
        "Не драматизируй, но и не отмахивайся.\n\n"
        "Хочешь глубже — бери платный расклад через кнопку ниже или через /buy."
    )
    mark_free_reading_used(user.id)
    save_reading(user.id, "basic", "Общий запрос", [card], text, True)
    await message.reply_text(text, parse_mode=ParseMode.HTML)


async def my_readings_from_message(message, user) -> None:
    rows = get_latest_readings(user.id)
    if not rows:
        await message.reply_text("Пока раскладов нет. Начни с /free или /buy.")
        return
    pieces = ["Твои последние расклады:\n"]
    for row in rows:
        created = row["created_at"].split("T")[0]
        q = row["question"] or "без вопроса"
        pieces.append(f"• #{row['id']} — {created} — {q}")
    pieces.append("\nНапиши /buy, чтобы получить новый расклад.")
    await message.reply_text("\n".join(pieces))


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    await query.answer()

    message = query.message
    user = update.effective_user
    if not message or not user:
        return

    if query.data == "free_card":
        await free_card_from_message(message, user)
        return
    if query.data == "buy_basic":
        await send_invoice(message.chat_id, context)
        return
    if query.data == "my_readings":
        await my_readings_from_message(message, user)
        return


async def precheckout_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.pre_checkout_query
    if not query:
        return
    if query.invoice_payload != "spread:basic":
        await query.answer(ok=False, error_message="Неизвестный товар. Попробуй ещё раз.")
        return
    await query.answer(ok=True)


async def successful_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if not message or not message.successful_payment:
        return
    payment = message.successful_payment
    user = update.effective_user
    upsert_user(user)
    save_payment(
        user.id,
        payload=payment.invoice_payload,
        status="paid",
        charge_id=payment.telegram_payment_charge_id,
        currency=payment.currency,
        total_amount=payment.total_amount,
    )
    await message.reply_text("Оплата прошла. Достаю карты и собираю мысли… 🔮")
    question = context.user_data.get("pending_question", "")
    spread_key = "basic"
    cards = draw_cards(spread_key)

    try:
        interpretation = await asyncio.to_thread(
            generate_interpretation,
            question,
            spread_key,
            cards,
            build_user_name(user),
        )
        save_reading(user.id, spread_key, question, cards, interpretation, False)
        positions = SPREADS[spread_key]["positions"]
        cards_text = "\n".join(f"{pos} — {card}" for pos, card in zip(positions, cards))
        final_text = (
            f"<b>Твой расклад готов</b>\n\n"
            f"<b>Карты:</b>\n{html.escape(cards_text)}\n\n"
            f"{html.escape(interpretation)}"
        )
        for chunk in split_text(final_text, 3800):
            await message.reply_text(chunk, parse_mode=ParseMode.HTML)
    except Exception as exc:
        logger.exception("Failed to generate reading: %s", exc)
        await message.reply_text(
            "Оплата зафиксирована, но на генерации я споткнулся. Напиши /my чуть позже или свяжись с поддержкой через /paysupport."
        )
    finally:
        context.user_data.pop("pending_question", None)


def split_text(text: str, max_len: int) -> List[str]:
    chunks: List[str] = []
    current = []
    current_len = 0
    for line in text.splitlines(keepends=True):
        if current_len + len(line) > max_len and current:
            chunks.append("".join(current))
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += len(line)
    if current:
        chunks.append("".join(current))
    return chunks


async def post_init(application: Application) -> None:
    logger.info("Bot started")


def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set")

    init_db()
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("free", free_command))
    application.add_handler(CommandHandler("buy", buy_command))
    application.add_handler(CommandHandler("my", my_command))
    application.add_handler(CommandHandler("paysupport", paysupport))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(PreCheckoutQueryHandler(precheckout_callback))
    application.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, successful_payment_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
