import os
import json
import base64
import asyncio
import logging
import threading
import gspread
from google.oauth2.service_account import Credentials
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask

logging.basicConfig(level=logging.INFO)

SHEET_ID = os.environ["GOOGLE_SHEET_ID"]
CREDS_B64 = os.environ["GOOGLE_CREDS_JSON_B64"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"] 

AI_MODEL = "anthropic/claude-sonnet-4.6"  

ai_client = OpenAI(
    base_url="https://polza.ai/api/v1",
    api_key=ANTHROPIC_API_KEY
)

def get_stock():
    creds_dict = json.loads(base64.b64decode(CREDS_B64).decode("utf-8"))
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets.readonly",
        "https://www.googleapis.com/auth/drive.readonly"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SHEET_ID).worksheet("Склад")
    return sheet.get_all_records()

def build_system_prompt():
    rows = get_stock()
    stock_text = "АКТУАЛЬНЫЕ ОСТАТКИ НА СКЛАДЕ:\n"
    for r in rows:
        if int(r.get("Количество", 0)) > 0:
            stock_text += f"• {r['Модель']} | Загиб: {r['Загиб']} | Хват: {r['Хват']} | Флекс: {r['Флекс']} | Кол-во: {r['Количество']} шт | Цена: {r['Цена']}₽\n"

    return f"""Ты — AI продавец магазина «Хоккейные клюшки ТОП».

ВАЖНО: Всегда отвечай только на русском языке, независимо от того на каком языке было предыдущее сообщение.

ТВОЯ ЗАДАЧА: помочь клиенту выбрать хоккейную клюшку и оформить заказ.

ЦЕНА: 9 900₽ за клюшку. С картой UDS первая клюшка 8 900₽.

{stock_text}

ПРОГРАММА ЛОЯЛЬНОСТИ UDS:
- 1 000 приветственных баллов при регистрации
- Кэшбэк до 7% с каждой покупки
- 1 балл = 1 рубль, списывать можно до 15% от покупки
- Оформить: t.me/UDS_hockey_sticks_top_bot

КАК ПОДОБРАТЬ КЛЮШКУ:
- Флекс = примерно 50% от веса игрока
- P28 — самый популярный загиб, подходит большинству
- Для новичков: флекс 65-70, загиб P28
- Для детей: флекс 40-55
- Левый хват — 79% продаж

ЕСЛИ КЛИЕНТ ПРИСЫЛАЕТ ФОТО КЛЮШКИ:
- Внимательно посмотри на надписи и логотип бренда на самой клюшке (CCM, Bauer, Warrior и т.д.)
- Не угадывай модель по предыдущему разговору — анализируй именно то что видно на текущем фото
- Если на фото видна другая модель, отличная от того что обсуждали ранее — скажи об этом прямо
- Сравни увиденное с нашим складом и скажи есть ли похожая модель
- Если не уверен — честно скажи что не можешь точно определить модель, предложи уточнить характеристики словами

ПРАВИЛА:
1. Отвечай коротко и по делу
2. Если клиент готов купить — попроси имя и телефон
3. Если клиент пишет «менеджер» — скажи что передаёшь
4. Не называй закупочные цены и имена поставщиков
5. Отвечай только на темы хоккея и клюшек"""

dialogs = {}

UDS_BUTTONS = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("📱 ТГ", url="https://t.me/UDS_hockey_sticks_top_bot"),
        InlineKeyboardButton("📱 MAX", url="https://max.ru/id164908988785_2_bot")
    ]
])

MANAGER_BUTTONS = InlineKeyboardMarkup([
    [InlineKeyboardButton("💬 Написать менеджеру", url="https://t.me/hockey_top_bot")]
])

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я AI помощник магазина «Хоккейные клюшки ТОП».\n\n"
        "Задай любой вопрос или пришли фото клюшки — помогу подобрать! 🏒📸"
    )

async def ask_ai(user_id, content):
    if user_id not in dialogs:
        dialogs[user_id] = []

    dialogs[user_id].append({"role": "user", "content": content})

    response = ai_client.chat.completions.create(
        model=AI_MODEL,
        messages=[
            {"role": "system", "content": build_system_prompt()}
        ] + dialogs[user_id][-10:]
    )

    answer = response.choices[0].message.content
    dialogs[user_id].append({"role": "assistant", "content": answer})
    return answer

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text

    manager_keywords = ["менеджер", "позвони", "перезвони", "оператор", "человек"]
    if any(w in text.lower() for w in manager_keywords):
        await update.message.reply_text(
            "Передаю тебя менеджеру — ответим быстро! 👇",
            reply_markup=MANAGER_BUTTONS
        )
        return

    try:
        await update.message.chat.send_action("typing")
        answer = await ask_ai(user_id, text)

        uds_keywords = ["uds", "удс", "карта", "скидка", "бонус", "кэшбэк", "8900", "8 900"]
        if any(w in answer.lower() for w in uds_keywords):
            await update.message.reply_text(answer, reply_markup=UDS_BUTTONS)
        else:
            await update.message.reply_text(answer)

    except Exception as e:
        logging.error(f"AI ошибка: {e}")
        await update.message.reply_text(
            "Что-то пошло не так 😔 Напиши «менеджер» — помогут вручную.",
            reply_markup=MANAGER_BUTTONS
        )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id

    try:
        await update.message.chat.send_action("typing")

        photo = update.message.photo[-1]
        photo_file = await photo.get_file()
        photo_bytes = await photo_file.download_as_bytearray()
        photo_b64 = base64.b64encode(bytes(photo_bytes)).decode("utf-8")

        caption = update.message.caption or "Клиент прислал фото клюшки. Внимательно посмотри на бренд и модель на этом конкретном фото, не путай с предыдущими сообщениями."

        # Каждое фото — отдельное сообщение, не накапливаем старые фото в истории
        content = [
            {"type": "text", "text": caption},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{photo_b64}"}
            }
        ]

        response = ai_client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role": "system", "content": build_system_prompt()},
                {"role": "user", "content": content}
            ]
        )

        answer = response.choices[0].message.content

        if user_id not in dialogs:
            dialogs[user_id] = []
        dialogs[user_id].append({"role": "user", "content": "[фото клюшки]"})
        dialogs[user_id].append({"role": "assistant", "content": answer})

        await update.message.reply_text(answer)

    except Exception as e:
        logging.error(f"Ошибка анализа фото: {e}")
        await update.message.reply_text(
            "Не получилось рассмотреть фото 😔 Опиши клюшку словами — модель, загиб, цвет.",
        )

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
    await asyncio.Event().wait()

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(run_bot())

if __name__ == "__main__":
    main()
