import os
import json
import base64
import asyncio
import logging
import threading
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = get_stock()
    text = "📦 Наличие на складе:\n\n"
    for r in rows:
        if int(r.get("Количество", 0)) > 0:
            text += f"• {r['Модель']} | {r['Загиб']} | {r['Хват']} | Флекс {r['Флекс']} | {r['Количество']} шт | {r['Цена']}₽\n"
    await update.message.reply_text(text)

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
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    await asyncio.Event().wait()

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    asyncio.run(run_bot())

if __name__ == "__main__":
    main()
