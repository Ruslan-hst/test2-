"""
ai_logic.py — системный промт и вызов Claude через polza.ai
"""

import os
import logging
from openai import OpenAI
from sheets import get_stock

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
AI_MODEL = "anthropic/claude-sonnet-4.6"

ai_client = OpenAI(
    base_url="https://polza.ai/api/v1",
    api_key=ANTHROPIC_API_KEY
)

CALL_MANAGER_MARKER = "[CALL_MANAGER]"

dialogs = {}


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

КОГДА ЗВАТЬ МЕНЕДЖЕРА (важно — будь внимателен к разнице):
- Если клиент ЯВНО просит позвать менеджера/человека/оператора ("позови менеджера", "хочу менеджера", "пусть менеджер ответит", "переключи на человека") — в САМОМ КОНЦЕ своего ответа добавь служебный маркер {CALL_MANAGER_MARKER} (он не будет виден клиенту, это техническая метка)
- Если клиент просто СПРАШИВАЕТ, может ли AI помочь, или упоминает слово "менеджер" в контексте вопроса ("ты сам можешь помочь или лучше позвать менеджера?", "а у вас есть живые менеджеры?") — это НЕ команда звать менеджера, отвечай на вопрос сам, маркер не добавляй
- Если не уверен — сначала попробуй помочь сам, маркер добавляй только при явной прямой просьбе

ПРАВИЛА:
1. Отвечай коротко и по делу
2. НЕ используй звёздочки, решётки и другую markdown-разметку — пиши обычным текстом
3. Используй эмодзи для акцентов вместо жирного текста (например: 🏒 для клюшек, 💰 для цены, ✅ для подтверждения)
4. Если клиент готов купить — попроси имя и телефон
5. Не называй закупочные цены и имена поставщиков
6. Отвечай только на темы хоккея и клюшек
7. Если в начале сообщения указан Telegram username отправителя @aliyalll — поприветствуй его и скажи, что Руслан передаёт, что любит Матулымку"""


def ask_ai_sync(user_id, content):
    if user_id not in dialogs:
        dialogs[user_id] = []

    dialogs[user_id].append({"role": "user", "content": content})

    response = ai_client.chat.completions.create(
        model=AI_MODEL,
        messages=[
            {"role": "system", "content": build_system_prompt()}
        ] + dialogs[user_id][-10:]
    )

    raw_answer = response.choices[0].message.content

    call_manager = CALL_MANAGER_MARKER in raw_answer
    clean_answer = raw_answer.replace(CALL_MANAGER_MARKER, "").strip()

    dialogs[user_id].append({"role": "assistant", "content": clean_answer})

    return clean_answer, call_manager


def ask_ai_with_image(image_content_block, caption_text):
    content = [
        {"type": "text", "text": caption_text},
        image_content_block
    ]

    response = ai_client.chat.completions.create(
        model=AI_MODEL,
        messages=[
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": content}
        ]
    )

    return response.choices[0].message.content
