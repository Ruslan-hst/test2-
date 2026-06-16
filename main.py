import os
import json
import base64
import asyncio
import logging
import threading
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from flask import Flask

logging.basicConfig(level=logging.INFO)

SHEET_ID = os.environ["GOOGLE_SHEET_ID"]
CREDS_B64 = os.environ["GOOGLE_CREDS_JSON_B64"]
BOT_TOKEN = os.environ["BOT_TOKEN"]

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

UDS_BUTTONS = InlineKeyboardMarkup([
    [
        InlineKeyboardButton("📱 ТГ", url="https://t.me/UDS_hockey_sticks_top_bot"),
        InlineKeyboardButton("📱 MAX", url="https://max.ru/id164908988785_2_bot")
    ]
])

MANAGER_BUTTONS = InlineKeyboardMarkup([
    [InlineKeyboardButton("💬 Написать менеджеру", url="https://t.me/hockey_top_bot")]
])

PRICE_TEXT = """💰 Цена клюшки — 9 900₽

🪪 Оформим карту UDS — дарим 1 000 приветственных бонусов.
Итого первая клюшка выходит всего 8 900₽ 🔥
Плюс кэшбэк с каждого заказа на следующие покупки.

♻️ Оформить карту — займёт менее 1 мин ⚡️"""

UDS_TEXT = """🎁 У нас программа лояльности UDS — бонусы и скидки с каждой покупки!

Что вы получаете:
⭐️ 1 000 приветственных баллов при регистрации
💸 Кэшбэк до 7% с каждой покупки
👥 500 баллов за приглашённого друга
🏒 1 балл = 1 рубль, списывать можно до 15% от покупки

Зарегистрируйтесь — баллы начислятся автоматически 👇
Баллы можно использовать уже на первый заказ! 🎯"""

MANAGER_TEXT = """📞 Передаю тебя менеджеру!

Напиши — ответим быстро 👇"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот магазина «Хоккейные клюшки ТОП».\n\n"
        "Напиши:\n"
        "• «наличие» — показать все клюшки на складе\n"
        "• «P28» — клюшки с загибом P28\n"
        "• «цена» — узнать цену\n"
        "• «скидка» — программа лояльности UDS\n"
        "• «менеджер» — связаться с менеджером"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()

    if any(w in text for w in ["наличие", "есть", "склад", "что есть"]):
        rows = get_stock()
        reply = "📦 Наличие на складе:\n\n"
        for r in rows:
            if int(r.get("Количество", 0)) > 0:
                reply += f"• {r['Модель']} | {r['Загиб']} | {r['Хват']} | Флекс {r['Флекс']} | {r['Количество']} шт | {r['Цена']}₽\n"
        await update.message.reply_text(reply)

    elif "p28" in text:
        rows = get_stock()
        reply = "📦 Клюшки с загибом P28:\n\n"
        found = False
        for r in rows:
            if r.get("Загиб") == "P28" and int(r.get("Количество", 0)) > 0:
                reply += f"• {r['Модель']} | {r['Хват']} | Флекс {r['Флекс']} | {r['Количество']} шт | {r['Цена']}₽\n"
                found = True
        if not found:
            reply = "К сожалению P28 сейчас нет в наличии 😔"
        await update.message.reply_text(reply)

    elif any(w in text for w in ["цена", "стоимость", "сколько стоит", "почём", "сколько"]):
        await update.message.reply_text(PRICE_TEXT, reply_markup=UDS_BUTTONS)

    elif any(w in text for w in ["скидка", "бонус", "кэшбэк", "uds", "удс", "карта"]):
        await update.message.reply_text(UDS_TEXT, reply_markup=UDS_BUTTONS)

    elif any(w in text for w in ["менеджер", "позвони", "перезвони", "человек", "оператор"]):
        await update.message.reply_text(MANAGER_TEXT, reply_markup=MANAGER_BUTTONS)

    else:
        await update.message.reply_text(
            "Не понял вопрос 😅\n\n"
            "Напиши:\n"
            "• «наличие» — показать склад\n"
            "• «P28» — клюшки P28\n"
            "• «цена» — узнать цену\n"
            "• «скидка» — программа лояльности\n"
            "• «менеджер» — связаться с менеджером"
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
