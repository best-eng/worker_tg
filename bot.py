import logging
import re
from datetime import datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, ConversationHandler, filters
)

# ═══════════════════════════════════════════════
#              НАСТРОЙКИ — МЕНЯЙ ЗДЕСЬ
# ═══════════════════════════════════════════════

BOT_TOKEN = "8633251064:AAGo4vRFCvpVLp6MqmRWS_dOGB5Z--JLmbo"  # Токен от @BotFather
ADMIN_ID = 534474540  # Твой Telegram user_id (@userinfobot)
TARGET_CHANNELS = [  # Можно @username, https://t.me/username, https://t.me/c/... или -100...
    "@JLNGSKGBLA",
    "https://t.me/c/2667578680/1367"
]
TIMEZONE = pytz.timezone("Asia/Yekaterinburg")  # Часовой пояс

# ═══════════════════════════════════════════════

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

AWAIT_REPOST_CONTENT = 1
AWAIT_SCHEDULE_TIME = 2
AWAIT_SCHEDULE_TEXT = 3


def normalize_target(value: str) -> str:
    value = value.strip()

    if not value:
        raise ValueError("Пустой target")

    # Уже готовый chat_id
    if re.fullmatch(r"-100\d+", value):
        return value

    # Публичный username
    if re.fullmatch(r"@\w{4,}", value):
        return value

    # Ссылка на публичный канал/группу: https://t.me/name или t.me/name
    m_public = re.fullmatch(r"(?:https?://)?t\.me/([A-Za-z0-9_]{4,})/?", value)
    if m_public:
        return f"@{m_public.group(1)}"

    # Ссылка вида https://t.me/c/2667578680/13699
    m_private_msg = re.fullmatch(r"(?:https?://)?t\.me/c/(\d+)(?:/\d+)?(?:/\d+)?/?", value)
    if m_private_msg:
        return f"-100{m_private_msg.group(1)}"

    raise ValueError(f"Неизвестный формат target: {value}")


def validate_targets(targets: list[str]) -> list[str]:
    normalized = []
    invalid = []

    for raw in targets:
        try:
            normalized.append(normalize_target(raw))
        except Exception as e:
            invalid.append(f"{raw} -> {e}")

    if invalid:
        for item in invalid:
            logger.error(f"Invalid TARGET_CHANNELS value: {item}")
        raise ValueError("Есть невалидные значения в TARGET_CHANNELS. Проверь логи.")

    return normalized


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return

    keyboard = [
        [InlineKeyboardButton("📤 Репост в каналы", callback_data="repost")],
        [InlineKeyboardButton("⏰ Запланировать сообщение", callback_data="schedule")],
    ]

    await update.message.reply_text(
        "👋 Привет! Выбери действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# ── РЕПОСТ (общая функция отправки) ──────────────────────────────────────────

async def do_repost(msg, context):
    errors = []

    for raw_channel in TARGET_CHANNELS:
        try:
            channel = normalize_target(raw_channel)

            if msg.photo:
                await context.bot.send_photo(
                    chat_id=channel,
                    photo=msg.photo[-1].file_id,
                    caption=msg.caption or "",
                    parse_mode="HTML"
                )
            elif msg.video:
                await context.bot.send_video(
                    chat_id=channel,
                    video=msg.video.file_id,
                    caption=msg.caption or "",
                    parse_mode="HTML"
                )
            elif msg.document and msg.document.mime_type and msg.document.mime_type.startswith("video"):
                await context.bot.send_document(
                    chat_id=channel,
                    document=msg.document.file_id,
                    caption=msg.caption or "",
                    parse_mode="HTML"
                )
            elif msg.text:
                await context.bot.send_message(
                    chat_id=channel,
                    text=msg.text,
                    parse_mode="HTML"
                )
            else:
                await msg.forward(chat_id=channel)

        except Exception as e:
            errors.append(f"{raw_channel}: {e}")
            logger.error(f"Repost error to {raw_channel}: {e}")

    return errors


async def repost_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "Отправь фото, видео с подписью или текст — разошлю по всем каналам.\n\n/cancel — отмена"
    )
    return AWAIT_REPOST_CONTENT


async def repost_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    errors = await do_repost(update.message, context)
    if errors:
        await update.message.reply_text("⚠️ Ошибки:\n" + "\n".join(errors))
    else:
        await update.message.reply_text(f"✅ Отправлено в {len(TARGET_CHANNELS)} канал(ов)!")
    return ConversationHandler.END


# Прямой репост фото/видео без нажатия кнопки
async def direct_repost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    errors = await do_repost(update.message, context)
    if errors:
        await update.message.reply_text("⚠️ Ошибки:\n" + "\n".join(errors))
    else:
        await update.message.reply_text(f"✅ Отправлено в {len(TARGET_CHANNELS)} канал(ов)!")


# ── ПЛАНИРОВЩИК ──────────────────────────────────────────────────────────────

async def schedule_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "Введи дату и время отправки в формате:\n"
        "<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n"
        "Пример: <code>10.05.2026 14:30</code>\n\n"
        "/cancel — отмена",
        parse_mode="HTML"
    )
    return AWAIT_SCHEDULE_TIME


async def schedule_get_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        dt_naive = datetime.strptime(update.message.text.strip(), "%d.%m.%Y %H:%M")
        dt_aware = TIMEZONE.localize(dt_naive)
        now = datetime.now(TIMEZONE)

        if dt_aware <= now:
            await update.message.reply_text("⛔ Это время уже прошло! Введи будущее время.")
            return AWAIT_SCHEDULE_TIME

        context.user_data["schedule_dt"] = dt_aware
        await update.message.reply_text(
            f"🕐 Время: <b>{dt_naive.strftime('%d.%m.%Y %H:%M')}</b> (Екатеринбург)\n\n"
            "Теперь отправь текст сообщения:",
            parse_mode="HTML"
        )
        return AWAIT_SCHEDULE_TEXT

    except ValueError:
        await update.message.reply_text(
            "❌ Неверный формат. Используй: <code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n"
            "Пример: <code>10.05.2026 14:30</code>",
            parse_mode="HTML"
        )
        return AWAIT_SCHEDULE_TIME


async def send_scheduled_message(ctx: ContextTypes.DEFAULT_TYPE):
    for raw_channel in TARGET_CHANNELS:
        try:
            channel = normalize_target(raw_channel)
            await ctx.bot.send_message(
                chat_id=channel,
                text=ctx.job.data,
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Scheduled error to {raw_channel}: {e}")


async def schedule_get_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    dt = context.user_data["schedule_dt"]
    now = datetime.now(TIMEZONE)
    delay = (dt - now).total_seconds()

    if delay <= 0:
        await update.message.reply_text("⛔ Время уже прошло. Начни заново.")
        return ConversationHandler.END

    context.job_queue.run_once(
        send_scheduled_message,
        when=delay,
        data=text,
        name=f"scheduled_{update.effective_user.id}_{int(dt.timestamp())}"
    )

    await update.message.reply_text(
        f"✅ Запланировано!\n"
        f"📅 <b>{dt.strftime('%d.%m.%Y %H:%M')}</b> (Екб)\n"
        f"📢 Каналов: <b>{len(TARGET_CHANNELS)}</b>",
        parse_mode="HTML"
    )
    return ConversationHandler.END


# ── ОТМЕНА ───────────────────────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено. /start — в меню.")
    return ConversationHandler.END


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    global TARGET_CHANNELS
    TARGET_CHANNELS = validate_targets(TARGET_CHANNELS)

    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(repost_start, pattern="^repost$"),
            CallbackQueryHandler(schedule_start, pattern="^schedule$"),
        ],
        states={
            AWAIT_REPOST_CONTENT: [
                MessageHandler(
                    (filters.PHOTO | filters.VIDEO | filters.Document.VIDEO | filters.TEXT) & ~filters.COMMAND,
                    repost_send
                )
            ],
            AWAIT_SCHEDULE_TIME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_get_time)
            ],
            AWAIT_SCHEDULE_TEXT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, schedule_get_text)
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv)
    app.add_handler(MessageHandler(
        filters.PHOTO | filters.VIDEO | filters.Document.VIDEO,
        direct_repost
    ))

    logger.info(f"Bot started. Targets: {TARGET_CHANNELS}")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
