"""
bitrix.py — интеграция с Битрикс24: создание сделок и дублирование переписки в комментарии.
"""

import os
import logging
import httpx

BITRIX_WEBHOOK_URL = os.environ.get("BITRIX_WEBHOOK_URL", "")
BITRIX_PORTAL_URL = os.environ.get("BITRIX_PORTAL_URL", "https://b24-9v9hth.bitrix24.ru")


def is_bitrix_enabled():
    return bool(BITRIX_WEBHOOK_URL)


def get_deal_link(deal_id):
    """Прямая ссылка на карточку сделки в интерфейсе Битрикс24."""
    return f"{BITRIX_PORTAL_URL}/crm/deal/details/{deal_id}/"


def create_deal(user_name, username, phone="", channel="Telegram"):
    """
    Создаёт новую сделку в Битрикс24 для нового клиента.
    Название формата: "AI Telegram | Имя клиента"
    Возвращает ID сделки (int) или None если не удалось создать.
    """
    if not is_bitrix_enabled():
        return None

    title = f"AI {channel} | {user_name}"

    comments = f"Клиент: {user_name}\nUsername: @{username}\nТелефон: {phone or 'не указан'}"

    payload = {
        "fields": {
            "TITLE": title,
            "SOURCE_ID": "WEB",
            "SOURCE_DESCRIPTION": f"{channel} бот — Хоккейные клюшки ТОП",
            "COMMENTS": comments,
        }
    }

    try:
        response = httpx.post(f"{BITRIX_WEBHOOK_URL}crm.deal.add.json", json=payload, timeout=10)
        result = response.json()
        if "result" in result:
            deal_id = result["result"]
            logging.info(f"Создана сделка Битрикс ID={deal_id} для {user_name}")
            return deal_id
        else:
            logging.error(f"Ошибка создания сделки Битрикс: {result}")
            return None
    except Exception as e:
        logging.error(f"Исключение при создании сделки Битрикс: {e}")
        return None


def add_comment(deal_id, author_label, text):
    """
    Добавляет комментарий в таймлайн сделки.
    author_label — например "Клиент" или "AI" или "Менеджер", чтобы различать кто писал.
    """
    if not is_bitrix_enabled() or not deal_id:
        return False

    payload = {
        "fields": {
            "ENTITY_ID": deal_id,
            "ENTITY_TYPE": "deal",
            "COMMENT": f"{author_label}: {text}"
        }
    }

    try:
        response = httpx.post(f"{BITRIX_WEBHOOK_URL}crm.timeline.comment.add.json", json=payload, timeout=10)
        result = response.json()
        if "result" in result:
            return True
        else:
            logging.error(f"Ошибка добавления комментария Битрикс: {result}")
            return False
    except Exception as e:
        logging.error(f"Исключение при добавлении комментария Битрикс: {e}")
        return False
