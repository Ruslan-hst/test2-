"""
main.py — запуск Telegram-бота и обработчики сообщений.
Вся логика AI вынесена в ai_logic.py, работа с Google Sheets — в sheets.py, Битрикс — в bitrix.py.
"""

import os
import base64
import asyncio
import logging
import threading
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask

from sheets import load_topic_mapping, save_topic_mapping, update_deal_id
from ai_logic import ask_ai_sync, ask_ai_with_image, dialogs
import bitrix

logging.basicConfig(level=logging.INFO)

BOT_TOKEN = os.environ["BOT_TOKEN"]
ADMIN_GROUP_ID = int(os.environ.get("ADMIN_GROUP_ID", "-1004320992345"))
ADMIN_PERSONAL_ID = int(os.environ.get("ADMIN_PERSONAL_ID", "469947146"))

PAUSE_MINUTES = 10
CHECK_INTERVAL_SECONDS = 120

client_topics, topic_to_client, topic_names, client_deals = load_topic_mapping()

pause_state = {}
escalated = {}

UDS_BUTTONS = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("📱 ТГ", url="https://t.me/UDS_hockey_sticks_top_bot"),
        InlineKeyboardButton("📱 MAX", url="https://max.ru/id164908988785_2_bot")
    ]
])


def get_topic_link(thread_id):
    group_id_for_link = str(ADMIN_GROUP_ID).replace("-100", "")
    return f"https://t.me/c/{group_id_for_link}/{thread_id}"


async def set_topic_status(bot, user_id, status: str):
    thread_id = client_topics.get(user_id)
    if not thread_id:
        return

    base_name = topic_names.get(user_id, "Клиент")

    if status == "paused":
        new_name = f"🔇 {base_name}"
    elif status == "escalated":
        new_name = f"⚠️ {base_name}"
    else:
        new_name = base_name

    new_name = new_name[:128]

    try:
        await bot.edit_forum_topic(
            chat_id=ADMIN_GROUP_ID,
            message_thread_id=thread_id,
            name=new_name
        )
    except Exception as e:
        logging.error(f"Ошибка переименования темы: {e}")


def sync_to_bitrix(user_id, author_label, text):
    deal_id = client_deals.get(user_id)
    if deal_id:
        bitrix.add_comment(deal_id, author_label, text)


async def get_or_create_topic(context, user_id, user_name, username):
    if user_id in client_topics:
        return client_topics[user_id]

    topic_name = f"{user_name} (@{username})" if username != "без username" else user_name
    topic_name = topic_name[:128]

    topic = await context.bot.create_forum_topic(
        chat_id=ADMIN_GROUP_ID,
        name=topic_name
    )

    thread_id = topic.message_thread_id
    client_topics[user_id] = thread_id
    topic_to_client[thread_id] = user_id
    topic_names[user_id] = topic_name

    deal_id = bitrix.create_deal(user_name, username)
    if deal_id:
        client_deals[user_id] = deal_id

    save_topic_mapping(user_id, thread_id, user_name, username, deal_id=deal_id or "")

    try:
        await context.bot.send_message(
            chat_id=ADMIN_PERSONAL_ID,
            text=f"🆕 Новый клиент в боте!\n\n👤 Имя: {user_name}\n📱 Username: @{username}\n\n💬 Тема создана в группе"
        )
    except Exception as e:
        logging.error(f"Ошибка уведомления о новом чате: {e}")

    return thread_id


def is_ai_paused(user_id):
    state = pause_state.get(user_id)
    return state is not None and state.get("paused", False)


def is_escalated(user_id):
    return escalated.get(user_id, False)


async def activate_manager_pause(context_bot, user_id, user_name, username, raw_text):
    pause_state[user_id] = {
        "paused": True,
        "last_manager_message_time": time.time(),
        "pending_client_messages": []
    }
    await set_topic_status(context_bot, user_id, "paused")

    try:
        thread_id = client_topics.get(user_id)
        topic_link = get_topic_link(thread_id) if thread_id else ""

        deal_id = client_deals.get(user_id)
        deal_link = bitrix.get_deal_link(deal_id) if deal_id else ""

        message_text = f"🔔 Клиент {user_name} (@{username}) просит менеджера!\n\nСообщение: {raw_text}\n\n👉 Перейти в чат: {topic_link}"
        if deal_link:
            message_text += f"\n📋 Сделка в Битрикс: {deal_link}"

        await context_bot.send_message(
            chat_id=ADMIN_PERSONAL_ID,
            text=message_text
        )
    except Exception as e:
        logging.error(f"Ошибка уведомления про менеджера: {e}")


async def activate_escalation(context_bot, user_id, user_name, username, raw_text):
    escalated[user_id] = True
    if user_id in pause_state:
        pause_state[user_id]["paused"] = False

    await set_topic_status(context_bot, user_id, "escalated")

    try:
        thread_id = client_topics.get(user_id)
        topic_link = get_topic_link(thread_id) if thread_id else ""

        deal_id = client_deals.get(user_id)
        deal_link = bitrix.get_deal_link(deal_id) if deal_id else ""

        message_text = (
            f"⚠️ ТРЕБУЕТСЯ ВНИМАНИЕ! Сложный случай у клиента {user_name} (@{username})\n\n"
            f"Сообщение: {raw_text}\n\n"
            f"AI приостановлен полностью для этого клиента.\n"
            f"Когда разберёшься — напиши /включить в этой теме.\n\n"
            f"👉 Перейти в чат: {topic_link}"
        )
        if deal_link:
            message_text += f"\n📋 Сделка в Битрикс: {deal_link}"

        await context_bot.send_message(
            chat_id=ADMIN_PERSONAL_ID,
            text=message_text
        )
    except Exception as e:
        logging.error(f"Ошибка уведомления про эскалацию: {e}")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я AI помощник магазина «Хоккейные клюшки ТОП».\n\n"
        "Задай любой вопрос или пришли фото клюшки — помогу подобрать! 🏒📸"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat_id == ADMIN_GROUP_ID:
        await handle_admin_reply(update, context)
        return

    user_id = update.message.from_user.id
    username = update.message.from_user.username or "без username"
    user_name = update.message.from_user.full_name or "Клиент"
    raw_text = update.message.text

    text = f"[Telegram username отправителя: @{username}]\n{raw_text}"

    try:
        thread_id = await get_or_create_topic(context, user_id, user_name, username)
        await context.bot.send_message(
            chat_id=ADMIN_GROUP_ID,
            message_thread_id=thread_id,
            text=f"👤 Клиент: {raw_text}"
        )
    except Exception as e:
        logging.error(f"Ошибка дублирования в группу: {e}")

    sync_to_bitrix(user_id, "Клиент", raw_text)

    if is_escalated(user_id):
        return

    if is_ai_paused(user_id):
        pause_state[user_id]["pending_client_messages"].append(raw_text)
        return

    try:
        await update.message.chat.send_action("typing")
        answer, call_manager, escalate, classification = ask_ai_sync(user_id, text)

        if escalate:
            await update.message.reply_text(answer)
            sync_to_bitrix(user_id, "AI", answer)
            await activate_escalation(context.bot, user_id, user_name, username, raw_text)
            return

        if call_manager:
            await update.message.reply_text("Передаю тебя менеджеру — ответим быстро! 👇")
            await activate_manager_pause(context.bot, user_id, user_name, username, raw_text)
            return

        if classification:
            deal_id = client_deals.get(user_id)
            if deal_id:
                bitrix.update_deal_classification(deal_id, classification)

        uds_keywords = ["uds", "удс", "карта", "скидка", "бонус", "кэшбэк", "8900", "8 900"]
        if any(w in answer.lower() for w in uds_keywords):
            await update.message.reply_text(answer, reply_markup=UDS_BUTTONS)
        else:
            await update.message.reply_text(answer)

        sync_to_bitrix(user_id, "AI", answer)

        try:
            thread_id = client_topics.get(user_id)
            if thread_id:
                await context.bot.send_message(
                    chat_id=ADMIN_GROUP_ID,
                    message_thread_id=thread_id,
                    text=f"🤖 AI: {answer}"
                )
        except Exception as e:
            logging.error(f"Ошибка дублирования ответа AI в группу: {e}")

    except Exception as e:
        logging.error(f"AI ошибка: {e}")


async def handle_admin_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    thread_id = update.message.message_thread_id
    if not thread_id or thread_id not in topic_to_client:
        return

    user_id = topic_to_client[thread_id]
    reply_text = update.message.text

    if reply_text and reply_text.strip() == "/включить":
        escalated[user_id] = False
        await set_topic_status(context.bot, user_id, "normal")
        await update.message.reply_text("✅ AI снова включён для этого клиента")
        return

    try:
        await context.bot.send_message(chat_id=user_id, text=reply_text)
        await update.message.reply_text("✅ Отправлено клиенту")

        sync_to_bitrix(user_id, "Менеджер", reply_text)

        if not is_escalated(user_id):
            if user_id not in pause_state:
                pause_state[user_id] = {"paused": True, "last_manager_message_time": time.time(), "pending_client_messages": []}
            else:
                pause_state[user_id]["paused"] = True
                pause_state[user_id]["last_manager_message_time"] = time.time()

            await set_topic_status(context.bot, user_id, "paused")

    except Exception as e:
        logging.error(f"Ошибка отправки ответа клиенту: {e}")
        await update.message.reply_text("❌ Не удалось отправить клиенту")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.chat_id == ADMIN_GROUP_ID:
        return

    user_id = update.message.from_user.id
    username = update.message.from_user.username or "без username"
    user_name = update.message.from_user.full_name or "Клиент"

    if is_escalated(user_id):
        try:
            thread_id = await get_or_create_topic(context, user_id, user_name, username)
            photo = update.message.photo[-1]
            await context.bot.send_photo(
                chat_id=ADMIN_GROUP_ID,
                message_thread_id=thread_id,
                photo=photo.file_id,
                caption="👤 Клиент отправил фото 📸 (AI на паузе из-за эскалации)"
            )
        except Exception as e:
            logging.error(f"Ошибка дублирования фото при эскалации: {e}")
        return

    if is_ai_paused(user_id):
        pause_state[user_id]["pending_client_messages"].append("[Клиент отправил фото]")
        try:
            thread_id = await get_or_create_topic(context, user_id, user_name, username)
            photo = update.message.photo[-1]
            await context.bot.send_photo(
                chat_id=ADMIN_GROUP_ID,
                message_thread_id=thread_id,
                photo=photo.file_id,
                caption="👤 Клиент отправил фото 📸"
            )
        except Exception as e:
            logging.error(f"Ошибка дублирования фото на паузе: {e}")
        return

    try:
        await update.message.chat.send_action("typing")

        photo = update.message.photo[-1]
        photo_file = await photo.get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        photo_b64 = base64.b64encode(bytes(photo_bytes)).decode("utf-8")

        caption_text = update.message.caption or "Клиент прислал фото клюшки. Внимательно посмотри на бренд и модель на этом конкретном фото, не путай с предыдущими сообщениями."
        caption = f"[Telegram username отправителя: @{username}]\n{caption_text}"

        image_block = {
            "type": "image_url",
            "image_url": {"url": f"data:image/jpeg;base64,{photo_b64}"}
        }

        answer = ask_ai_with_image(image_block, caption)

        if user_id not in dialogs:
            dialogs[user_id] = []
        dialogs[user_id].append({"role": "user", "content": "[фото клюшки]"})
        dialogs[user_id].append({"role": "assistant", "content": answer})

        await update.message.reply_text(answer)

        sync_to_bitrix(user_id, "Клиент", "[отправил фото клюшки]")
        sync_to_bitrix(user_id, "AI", answer)

        try:
            thread_id = await get_or_create_topic(context, user_id, user_name, username)
            await context.bot.send_message(
                chat_id=ADMIN_GROUP_ID,
                message_thread_id=thread_id,
                text="👤 Клиент отправил фото 📸"
            )
            await context.bot.send_photo(
                chat_id=ADMIN_GROUP_ID,
                message_thread_id=thread_id,
                photo=photo.file_id
            )
            await context.bot.send_message(
                chat_id=ADMIN_GROUP_ID,
                message_thread_id=thread_id,
                text=f"🤖 AI: {answer}"
            )
        except Exception as e:
            logging.error(f"Ошибка дублирования фото в группу: {e}")

    except Exception as e:
        logging.error(f"Ошибка анализа фото: {e}")


async def pause_checker_loop(application):
    while True:
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        now = time.time()

        for user_id, state in list(pause_state.items()):
            if is_escalated(user_id):
                continue

            if not state.get("paused"):
                continue

            elapsed = now - state["last_manager_message_time"]
            if elapsed < PAUSE_MINUTES * 60:
                continue

            pending = state.get("pending_client_messages", [])
            if not pending:
                state["paused"] = False
                await set_topic_status(application.bot, user_id, "normal")
                continue

            try:
                combined_text = "\n".join(pending)
                content = f"[Сообщения клиента пока ты не отвечал]\n{combined_text}"

                answer, call_manager, escalate, classification = ask_ai_sync(user_id, content)

                await application.bot.send_message(chat_id=user_id, text=answer)
                sync_to_bitrix(user_id, "AI", answer)

                if classification:
                    deal_id = client_deals.get(user_id)
                    if deal_id:
                        bitrix.update_deal_classification(deal_id, classification)

                thread_id = client_topics.get(user_id)
                if thread_id:
                    await application.bot.send_message(
                        chat_id=ADMIN_GROUP_ID,
                        message_thread_id=thread_id,
                        text=f"🤖 AI (вернулся после паузы): {answer}"
                    )

                state["paused"] = False
                state["pending_client_messages"] = []

                if escalate:
                    await activate_escalation(application.bot, user_id, topic_names.get(user_id, "Клиент"), "", combined_text)
                elif call_manager:
                    state["paused"] = True
                    state["last_manager_message_time"] = time.time()
                    await set_topic_status(application.bot, user_id, "paused")
                else:
                    await set_topic_status(application.bot, user_id, "normal")

            except Exception as e:
                logging.error(f"Ошибка при возобновлении AI после паузы: {e}")


flask_app = Flask(__name__)


@flask_app.route("/")
def index():
    return "OK"


def run_flask():
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port, use_reloader=False)


async def run_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    asyncio.create_task(pause_checker_loop(app))

    await asyncio.Event().wait()


def main():
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
