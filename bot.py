import os
import logging
from datetime import datetime
import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, ConversationHandler, filters
)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID  = int(os.environ["ADMIN_ID"])
TARGET_CHANNELS = os.environ["TARGET_CHANNELS"].split(",")
TIMEZONE = pytz.timezone("Asia/Yekaterinburg")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

AWAIT_REPOST_CONTENT = 1
AWAIT_SCHEDULE_TIME  = 2
AWAIT_SCHEDULE_TEXT  = 3


def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_user.id != ADMIN_ID:
            await update.message.reply_text("⛔ Нет доступа.")
            return
        return await func(update, context)
    return wrapper


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


# ── REPOST FLOW ──────────────────────────────────────────────────────────────

async def repost_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "Отправь видео с подписью (caption) или просто текст — "
        "я разошлю по всем каналам.\n\n/cancel — отмена"
    )
    return AWAIT_REPOST_CONTENT


async def repost_send(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message
    errors = []

    for channel in TARGET_CHANNELS:
        channel = channel.strip()
        try:
            if msg.video:
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
            errors.append(f"{channel}: {e}")
            logger.error(f"Repost error to {channel}: {e}")

    if errors:
        await msg.reply_text("⚠️ Ошибки при отправке:\n" + "\n".join(errors))
    else:
        await msg.reply_text(f"✅ Успешно отправлено в {len(TARGET_CHANNELS)} канал(ов)!")

    return ConversationHandler.END


# ── SCHEDULE FLOW ────────────────────────────────────────────────────────────

async def schedule_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text(
        "Введи дату и время отправки в формате:\n"
        "<code>ДД.ММ.ГГГГ ЧЧ:ММ</code>\n\n"
        "Пример: <code>10.05.2026 14:30</code>\n\n/cancel — отмена",
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
            "Теперь отправь текст сообщения (поддерживается HTML-разметка):",
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


async def schedule_get_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    dt   = context.user_data["schedule_dt"]
    now  = datetime.now(TIMEZONE)
    delay = (dt - now).total_seconds()

    if delay <= 0:
        await update.message.reply_text("⛔ Время уже прошло пока ты писал. Начни заново.")
        return ConversationHandler.END

    async def send_scheduled(ctx: ContextTypes.DEFAULT_TYPE):
        errs = []
        for channel in TARGET_CHANNELS:
            channel = channel.strip()
            try:
                await ctx.bot.send_message(
                    chat_id=channel,
                    text=ctx.job.data,
                    parse_mode="HTML"
                )
            except Exception as e:
                errs.append(f"{channel}: {e}")
                logger.error(f"Scheduled send error to {channel}: {e}")

    context.job_queue.run_once(
        send_scheduled,
        when=delay,
        data=text,
        name=f"scheduled_{update.effective_user.id}_{int(dt.timestamp())}"
    )

    await update.message.reply_text(
        f"✅ Сообщение запланировано!\n"
        f"📅 <b>{dt.strftime('%d.%m.%Y %H:%M')}</b> (Екб)\n"
        f"📢 Будет отправлено в <b>{len(TARGET_CHANNELS)}</b> канал(ов)",
        parse_mode="HTML"
    )
    return ConversationHandler.END


# ── CANCEL ───────────────────────────────────────────────────────────────────

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Действие отменено. /start — вернуться в меню.")
    return ConversationHandler.END


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(repost_start,   pattern="^repost$"),
            CallbackQueryHandler(schedule_start, pattern="^schedule$"),
        ],
        states={
            AWAIT_REPOST_CONTENT: [
                MessageHandler(
                    (filters.VIDEO | filters.Document.VIDEO | filters.TEXT) & ~filters.COMMAND,
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

    logger.info("Bot started...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
