import logging
import re
from dataclasses import dataclass
from datetime import datetime

import pytz
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, ConversationHandler, filters
)

BOT_TOKEN = "8633251064:AAGo4vRFCvpVLp6MqmRWS_dOGB5Z--JLmbo"
ADMIN_ID = 534474540

TARGET_CHANNELS = [
    "@JLNGSKGBLA",
    "https://t.me/c/2667578680/1367/3184",
    # "-1002667578680",
    # "https://t.me/c/2667578680/25/1367",   # topic_id = 25
]

TIMEZONE = pytz.timezone("Asia/Yekaterinburg")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

AWAIT_REPOST_CONTENT = 1
AWAIT_SCHEDULE_TIME = 2
AWAIT_SCHEDULE_TEXT = 3


@dataclass
class Target:
    raw: str
    chat_id: str
    message_thread_id: int | None = None
    is_general_topic: bool = False


def normalize_target(value: str) -> Target:
    value = value.strip()

    if not value:
        raise ValueError("Пустой target")

    if re.fullmatch(r"-100\d+", value):
        return Target(raw=value, chat_id=value)

    if re.fullmatch(r"@\w{4,}", value):
        return Target(raw=value, chat_id=value)

    m_public = re.fullmatch(r"(?:https?://)?t\.me/([A-Za-z0-9_]{4,})/?", value)
    if m_public:
        return Target(raw=value, chat_id=f"@{m_public.group(1)}")

    m_private_topic = re.fullmatch(
        r"(?:https?://)?t\.me/c/(\d+)/(\d+)/(\d+)/?",
        value
    )
    if m_private_topic:
        internal_chat_id = m_private_topic.group(1)
        topic_id = int(m_private_topic.group(2))
        return Target(
            raw=value,
            chat_id=f"-100{internal_chat_id}",
            message_thread_id=topic_id,
            is_general_topic=(topic_id == 1)
        )

    m_private_msg = re.fullmatch(
        r"(?:https?://)?t\.me/c/(\d+)/(\d+)/?",
        value
    )
    if m_private_msg:
        internal_chat_id = m_private_msg.group(1)
        return Target(
            raw=value,
            chat_id=f"-100{internal_chat_id}",
            message_thread_id=None,
            is_general_topic=True
        )

    raise ValueError(f"Неизвестный формат target: {value}")


def validate_targets(targets: list[str]) -> list[Target]:
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


async def send_to_target(
    bot,
    target: Target,
    *,
    text=None,
    photo=None,
    video=None,
    document=None,
    caption=None,
    forward_message=None
):
    kwargs = {"chat_id": target.chat_id}

    if target.message_thread_id is not None and not target.is_general_topic:
        kwargs["message_thread_id"] = target.message_thread_id

    if photo:
        await bot.send_photo(
            photo=photo,
            caption=caption or "",
            parse_mode="HTML",
            **kwargs
        )
    elif video:
        await bot.send_video(
            video=video,
            caption=caption or "",
            parse_mode="HTML",
            **kwargs
        )
    elif document:
        await bot.send_document(
            document=document,
            caption=caption or "",
            parse_mode="HTML",
            **kwargs
        )
    elif text:
        await bot.send_message(
            text=text,
            parse_mode="HTML",
            **kwargs
        )
    elif forward_message:
        await forward_message.forward(chat_id=target.chat_id)
    else:
        raise ValueError("Нет данных для отправки")


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


async def do_repost(msg, context):
    errors = []

    for target in TARGET_CHANNELS:
        try:
            if msg.photo:
                await send_to_target(
                    context.bot,
                    target,
                    photo=msg.photo[-1].file_id,
                    caption=msg.caption or ""
                )
            elif msg.video:
                await send_to_target(
                    context.bot,
                    target,
                    video=msg.video.file_id,
                    caption=msg.caption or ""
                )
            elif msg.document and msg.document.mime_type and msg.document.mime_type.startswith("video"):
                await send_to_target(
                    context.bot,
                    target,
                    document=msg.document.file_id,
                    caption=msg.caption or ""
                )
            elif msg.text:
                await send_to_target(
                    context.bot,
                    target,
                    text=msg.text
                )
            else:
                await send_to_target(
                    context.bot,
                    target,
                    forward_message=msg
                )

        except Exception as e:
            errors.append(f"{target.raw}: {e}")
            logger.error(f"Repost error to {target.raw}: {e}")

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


async def direct_repost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    errors = await do_repost(update.message, context)

    if errors:
        await update.message.reply_text("⚠️ Ошибки:\n" + "\n".join(errors))
    else:
        await update.message.reply_text(f"✅ Отправлено в {len(TARGET_CHANNELS)} канал(ов)!")


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
    for target in TARGET_CHANNELS:
        try:
            await send_to_target(
                ctx.bot,
                target,
                text=ctx.job.data
            )
        except Exception as e:
            logger.error(f"Scheduled error to {target.raw}: {e}")


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


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Отменено. /start — в меню.")
    return ConversationHandler.END


def main():
    global TARGET_CHANNELS
    TARGET_CHANNELS = validate_targets(TARGET_CHANNELS)

    for target in TARGET_CHANNELS:
        logger.info(
            f"Loaded target: raw={target.raw}, chat_id={target.chat_id}, "
            f"message_thread_id={target.message_thread_id}, "
            f"is_general_topic={target.is_general_topic}"
        )

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

    logger.info("Bot started...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
