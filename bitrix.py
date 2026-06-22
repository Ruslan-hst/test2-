"""
bitrix.py — интеграция с Битрикс24: создание сделок и дублирование переписки в комментарии.
"""

import os
import logging
import httpx

BITRIX_WEBHOOK_URL = os.environ.get("BITRIX_WEBHOOK_URL", "")


def is_bitrix_enabled():
    return bool(BITRIX_WEBHOOK_URL)


def create_deal(user_name, username, phone=""):
    """
    Создаёт новую сделку в Битрикс24 для нового клиента.
    Возвращает ID сделки (int) или None если не удалось создать.
    """
    if not is_bitrix_enabled():
        return None

    title = f"Telegram | {user_name}"
    if username and username != "без username":
        title += f" (@{username})"

    payload = {
        "fields": {
            "TITLE": title,
            "SOURCE_ID": "WEB",
            "SOURCE_DESCRIPTION": "Telegram бот — Хоккейные клюшки ТОП",
            "COMMENTS": f"Клиент: {user_name}\nUsername: @{username}\nТелефон: {phone or 'не указан'}",
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
