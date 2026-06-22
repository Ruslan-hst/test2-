"""
sheets.py — все функции работы с Google Sheets
(остатки склада + связь клиентов с темами в группе)
"""

import os
import json
import base64
import logging
import time
import gspread
from google.oauth2.service_account import Credentials

SHEET_ID = os.environ["GOOGLE_SHEET_ID"]
CREDS_B64 = os.environ["GOOGLE_CREDS_JSON_B64"]

_stock_cache = {"data": None, "timestamp": 0}
STOCK_CACHE_SECONDS = 120


def get_sheets_client():
    creds_dict = json.loads(base64.b64decode(CREDS_B64).decode("utf-8"))
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    return gspread.authorize(creds)


def get_stock():
    now = time.time()
    if _stock_cache["data"] is not None and (now - _stock_cache["timestamp"]) < STOCK_CACHE_SECONDS:
        return _stock_cache["data"]

    try:
        client = get_sheets_client()
        sheet = client.open_by_key(SHEET_ID).worksheet("Склад")
        data = sheet.get_all_records()
        _stock_cache["data"] = data
        _stock_cache["timestamp"] = now
        return data
    except Exception as e:
        logging.error(f"Ошибка получения склада: {e}")
        if _stock_cache["data"] is not None:
            return _stock_cache["data"]
        return []


def get_chats_sheet():
    client = get_sheets_client()
    return client.open_by_key(SHEET_ID).worksheet("Чаты_ТГ")


def load_topic_mapping():
    try:
        sheet = get_chats_sheet()
        rows = sheet.get_all_records()
        client_topics = {}
        topic_to_client = {}
        topic_names = {}
        for r in rows:
            uid = int(r["user_id"])
            tid = int(r["thread_id"])
            client_topics[uid] = tid
            topic_to_client[tid] = uid
            topic_names[uid] = r.get("user_name", "Клиент")
        return client_topics, topic_to_client, topic_names
    except Exception as e:
        logging.error(f"Ошибка загрузки маппинга из Sheets: {e}")
        return {}, {}, {}


def save_topic_mapping(user_id, thread_id, user_name, username, phone=""):
    try:
        sheet = get_chats_sheet()
        sheet.append_row([str(user_id), str(thread_id), user_name, username, phone])
    except Exception as e:
        logging.error(f"Ошибка сохранения маппинга в Sheets: {e}")
