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
    Стадия — "AI" (UC_46YL1F), чтобы сразу было видно что сделку завёл бот.
    Возвращает ID сделки (int) или None если не удалось создать.
    """
    if not is_bitrix_enabled():
        return None

    title = f"AI {channel} | {user_name}"

    comments = f"Клиент: {user_name}\nUsername: @{username}\nТелефон: {phone or 'не указан'}"

    payload = {
        "fields": {
            "TITLE": title,
            "STAGE_ID": "UC_46YL1F",
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


# Поле "❗Классификация❗" — список enumeration, каждому варианту соответствует ID
CLASSIFICATION_FIELD = "UF_CRM_1770200849934"
CLASSIFICATION_IDS = {
    "JR": "371",       # JR 20-50
    "INT": "373",      # INT 55-65
    "SR": "375",       # SR 70 и выше
    "ДЕШЕВЫЕ": "377",  # Дешевые
    "ОРИГИНАЛЫ": "379",  # Оригинал
    "ВРАТАРСКИЕ": "381",  # Вратари
}


def update_deal_classification(deal_id, segment_code):
    """
    Записывает классификацию в карточку сделки.
    segment_code — один из: JR, INT, SR, ДЕШЕВЫЕ, ОРИГИНАЛЫ, ВРАТАРСКИЕ
    """
    if not is_bitrix_enabled() or not deal_id:
        return False

    field_value = CLASSIFICATION_IDS.get(segment_code.upper())
    if not field_value:
        logging.error(f"Неизвестный код сегмента классификации: {segment_code}")
        return False

    payload = {
        "id": deal_id,
        "fields": {
            CLASSIFICATION_FIELD: field_value
        }
    }

    try:
        response = httpx.post(f"{BITRIX_WEBHOOK_URL}crm.deal.update.json", json=payload, timeout=10)
        result = response.json()
        if result.get("result"):
            logging.info(f"Классификация {segment_code} записана в сделку {deal_id}")
            return True
        else:
            logging.error(f"Ошибка записи классификации Битрикс: {result}")
            return False
    except Exception as e:
        logging.error(f"Исключение при записи классификации Битрикс: {e}")
        return False
