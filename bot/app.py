from __future__ import annotations

import asyncio
import base64
import os

from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

from bot.backend_api import BackendApi


BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
ACTIVE_TASKS: dict[int, str] = {}
LAST_EVENT_INDEX: dict[int, int] = {}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Telegram frontend connected. Send a task and the backend will pass it to the Windows client."
    )


async def stream_task_updates(
    api: BackendApi,
    chat_id: int,
    task_id: str,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    while True:
        task = api.get_task(task_id)
        events = api.list_events(task_id)
        start_index = LAST_EVENT_INDEX.get(chat_id, 0)

        for event in events[start_index:]:
            image_base64 = event.get("image_base64")
            if event.get("event_type") == "screenshot" and image_base64:
                try:
                    image_data = base64.b64decode(image_base64)
                    await context.bot.send_photo(
                        chat_id=chat_id,
                        photo=image_data,
                        caption=event.get("message", "Screenshot"),
                    )
                except Exception:
                    await context.bot.send_message(
                        chat_id=chat_id,
                        text=event.get("message", "Screenshot event received."),
                    )
            elif event.get("message"):
                await context.bot.send_message(chat_id=chat_id, text=event["message"])

        LAST_EVENT_INDEX[chat_id] = len(events)

        if task.status.value in {"done", "failed"}:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"Task finished with status `{task.status.value}`.\n{task.result_text}",
                parse_mode="Markdown",
            )
            ACTIVE_TASKS.pop(chat_id, None)
            LAST_EVENT_INDEX.pop(chat_id, None)
            return

        await asyncio.sleep(2)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    api = BackendApi(BACKEND_URL)
    chat_id = update.effective_chat.id
    text = update.message.text

    if chat_id in ACTIVE_TASKS:
        ok = api.interrupt_task(ACTIVE_TASKS[chat_id], text)
        await update.message.reply_text(
            "Interrupt sent to active task." if ok else "No active task found on backend."
        )
        return

    task = api.submit_message(chat_id=chat_id, text=text)
    ACTIVE_TASKS[chat_id] = task.id
    LAST_EVENT_INDEX[chat_id] = 0
    await update.message.reply_text(f"Task accepted: {task.id}")
    context.application.create_task(stream_task_updates(api, chat_id, task.id, context))


def main() -> None:
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))
    application.run_polling()


if __name__ == "__main__":
    main()
