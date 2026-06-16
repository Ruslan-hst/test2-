import os
import json
import base64
import logging
import gspread
from google.oauth2.service_account import Credentials
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

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

app = ApplicationBuilder().token(BOT_TOKEN).bu
