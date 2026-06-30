"""
sheets.py — все функции работы с Google Sheets
(остатки склада + связь клиентов с темами в группе + связь со сделками Битрикс + данные для касаний)
"""

import os
import json
import base64
import logging
import time
from datetime import datetime, timezone
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
    """Загружает все связи user_id <-> thread_id <-> deal_id из Google Sheets при старте бота."""
    try:
        sheet = get_chats_sheet()
        rows = sheet.get_all_records()
        client_topics = {}
        topic_to_client = {}
        topic_names = {}
        client_deals = {}
        for r in rows:
            uid = int(r["user_id"])
            tid = int(r["thread_id"])
            client_topics[uid] = tid
            topic_to_client[tid] = uid
            topic_names[uid] = r.get("user_name", "Клиент")
            deal_id_raw = r.get("deal_id", "")
            if deal_id_raw:
                client_deals[uid] = int(deal_id_raw)
        return client_topics, topic_to_client, topic_names, client_deals
    except Exception as e:
        logging.error(f"Ошибка загрузки маппинга из Sheets: {e}")
        return {}, {}, {}, {}


def save_topic_mapping(user_id, thread_id, user_name, username, phone="", deal_id=""):
    """Сохраняет новую связь user_id <-> thread_id <-> deal_id в Google Sheets.
    Также сразу заполняет last_client_message_time (этим сообщением клиент только что написал)
    и touch_number=0, status="active" для нового клиента."""
    try:
        sheet = get_chats_sheet()
        now_iso = datetime.now(timezone.utc).isoformat()
        sheet.append_row([
            str(user_id), str(thread_id), user_name, username, phone, str(deal_id),
            now_iso,  # G — last_client_message_time
            "",       # H — last_manager_message_time
            "0",      # I — touch_number
            "active"  # J — status
        ])
    except Exception as e:
        logging.error(f"Ошибка сохранения маппинга в Sheets: {e}")


def update_deal_id(user_id, deal_id):
    """Обновляет deal_id для существующей строки клиента (если сделка создалась позже темы)."""
    try:
        sheet = get_chats_sheet()
        rows = sheet.get_all_records()
        for idx, r in enumerate(rows, start=2):
            if int(r["user_id"]) == user_id:
                sheet.update_cell(idx, 6, str(deal_id))  # колонка F = 6
                return
    except Exception as e:
        logging.error(f"Ошибка обновления deal_id в Sheets: {e}")


def _find_row_index(sheet, user_id):
    """Вспомогательная функция — находит номер строки клиента в таблице (или None)."""
    rows = sheet.get_all_records()
    for idx, r in enumerate(rows, start=2):
        if int(r["user_id"]) == user_id:
            return idx
    return None


def update_last_client_message(user_id):
    """Обновляет время последнего сообщения КЛИЕНТА и сбрасывает touch_number на 0 (клиент снова активен)."""
    try:
        sheet = get_chats_sheet()
        idx = _find_row_index(sheet, user_id)
        if idx:
            now_iso = datetime.now(timezone.utc).isoformat()
            sheet.update_cell(idx, 7, now_iso)    # G = last_client_message_time
            sheet.update_cell(idx, 9, "0")         # I = touch_number сброс, клиент написал сам
            sheet.update_cell(idx, 10, "active")   # J = status
    except Exception as e:
        logging.error(f"Ошибка обновления last_client_message_time: {e}")


def update_last_manager_message(user_id):
    """Обновляет время последнего сообщения МЕНЕДЖЕРА (когда Руслан написал в теме)."""
    try:
        sheet = get_chats_sheet()
        idx = _find_row_index(sheet, user_id)
        if idx:
            now_iso = datetime.now(timezone.utc).isoformat()
            sheet.update_cell(idx, 8, now_iso)  # H = last_manager_message_time
    except Exception as e:
        logging.error(f"Ошибка обновления last_manager_message_time: {e}")


def update_touch_number(user_id, touch_number):
    """Обновляет touch_number для клиента (вызывается после успешной отправки касания)."""
    try:
        sheet = get_chats_sheet()
        idx = _find_row_index(sheet, user_id)
        if idx:
            sheet.update_cell(idx, 9, str(touch_number))  # I = touch_number
    except Exception as e:
        logging.error(f"Ошибка обновления touch_number: {e}")
