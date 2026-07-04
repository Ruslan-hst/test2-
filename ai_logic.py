"""
ai_logic.py - системный промт и вызов Claude через polza.ai
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
ESCALATE_MARKER = "[ESCALATE]"
CLASSIFY_PREFIX = "[CLASSIFY:"
VALID_SEGMENTS = ["SR", "INT", "JR", "ДЕШЕВЫЕ", "ОРИГИНАЛЫ", "ВРАТАРСКИЕ"]

dialogs = {}


def build_system_prompt():
    rows = get_stock()

    stock_text = "АКТУАЛЬНЫЕ ОСТАТКИ НА СКЛАДЕ:\n"
    for r in rows:
        total = int(r.get("ОБЩИЙ", 0))
        if total <= 0:
            continue
        brand = r.get("Бренд", "")
        model = r.get("Модель", "")
        hand = r.get("Хват", "")
        bend = r.get("Загиб", "")
        flex = r.get("Флекс", "")
        color = r.get("Цвет", "")
        price = r.get("Цена", "9900")

        msk2 = int(r.get("МСК2 (Игорь)", 0))
        mo = int(r.get("МО (Максим)", 0))
        if msk2 > 0 and mo > 0:
            ship_from = "Москва или Раменское"
        elif msk2 > 0:
            ship_from = "Москва"
        else:
            ship_from = "Раменское"

        hand_display = "Левый" if hand == "L" else "Правый"
        color_note = f" | Цвет: {color}" if color and color not in ("standard", "уточнить", "уточнить у Игоря") else ""

        stock_text += (
            f"• {brand} {model} | {bend} | {hand_display} | Флекс: {flex}"
            f"{color_note} | {total} шт | {price}руб | Отправка из: {ship_from}\n"
        )

    prompt = (
        "Ты - AI продавец магазина Хоккейные клюшки ТОП.\n\n"
        "ВАЖНО: Всегда отвечай только на русском языке.\n\n"
        "ТВОЯ ЗАДАЧА: помочь клиенту выбрать хоккейную клюшку и оформить заказ.\n\n"
        "ЦЕНА: 9 900 руб за клюшку. С картой UDS первая клюшка 8 900 руб.\n\n"
        + stock_text +
        "\nИНФОРМАЦИЯ О МАГАЗИНЕ:\n"
        "- Офлайн магазин: г. Казань, пер. Односторонки Гривки 10\n"
        "- 2ГИС: https://go.2gis.com/DT48h\n"
        "- Яндекс Карты: https://yandex.ru/maps/-/CTeGb8M1\n"
        "- Доставка возможна по всей России. Отправка из Москвы или Раменского в зависимости от наличия.\n"
        "- Если клиент спрашивает откуда будет отправка - смотри в колонку Отправка из по конкретной позиции и скажи город. Название поставщиков клиенту НЕ называй.\n\n"
        "ПРОГРАММА ЛОЯЛЬНОСТИ UDS:\n"
        "- 1 000 приветственных баллов при регистрации\n"
        "- Кэшбэк до 7% с каждой покупки\n"
        "- 1 балл = 1 рубль, списывать можно до 15% от покупки\n"
        "- Оформить: t.me/UDS_hockey_sticks_top_bot\n\n"
        "КАК ПОДОБРАТЬ КЛЮШКУ:\n"
        "- Флекс = примерно 50% от веса игрока\n"
        "- P28 - самый популярный загиб, подходит большинству\n"
        "- Для новичков: флекс 65-70, загиб P28\n"
        "- Для детей: флекс 40-55\n"
        "- Левый хват - 79% продаж\n"
        "- SR сегмент: флекс 70 и выше (взрослый/сильный игрок)\n"
        "- INT сегмент: флекс 55-65 (подросток)\n"
        "- JR сегмент: флекс 20-50 (ребёнок/юниор)\n\n"
        "ЕСЛИ КЛИЕНТ ПРИСЫЛАЕТ ФОТО КЛЮШКИ:\n"
        "- Внимательно посмотри на надписи и логотип бренда на самой клюшке (CCM, Bauer и т.д.)\n"
        "- Не угадывай модель по предыдущему разговору - анализируй именно то что видно на текущем фото\n"
        "- Если на фото видна другая модель, отличная от того что обсуждали ранее - скажи об этом прямо\n"
        "- Сравни увиденное с нашим складом и скажи есть ли похожая модель\n"
        "- Если не уверен - честно скажи что не можешь точно определить модель\n\n"
        "КЛАССИФИКАЦИЯ ПОТРЕБНОСТИ (важно - записывается в CRM):\n"
        "Как только понимаешь что именно ищет клиент - определи сегмент и добавь в конец ответа маркер "
        + CLASSIFY_PREFIX + "СЕГМЕНТ] (например " + CLASSIFY_PREFIX + "SR]). Этот маркер не виден клиенту.\n"
        "Возможные сегменты:\n"
        "- SR - флекс 70 и выше\n"
        "- INT - флекс 55-65\n"
        "- JR - флекс 20-50\n"
        "- ДЕШЕВЫЕ - бюджет 2-6 тыс руб, ищет восстановленную/б.у.\n"
        "- ОРИГИНАЛЫ - хочет только оригинал, не реплику\n"
        "- ВРАТАРСКИЕ - спрашивает про вратарскую клюшку или форму\n"
        "Приоритет: ОРИГИНАЛЫ и ВРАТАРСКИЕ и ДЕШЕВЫЕ перекрывают определение по флексу.\n"
        "Ставь маркер ОДИН РАЗ, как только определился.\n\n"
        "КОГДА ЗВАТЬ МЕНЕДЖЕРА - ОБЫЧНАЯ ПРОСЬБА:\n"
        "- Если клиент ЯВНО просит позвать менеджера - в КОНЦЕ ответа добавь маркер " + CALL_MANAGER_MARKER + "\n"
        "- Если клиент просто спрашивает могу ли я помочь - это вопрос, отвечай сам, маркер не добавляй\n\n"
        "КОГДА ЭСКАЛИРОВАТЬ - СЕРЬЁЗНЫЕ СЛУЧАИ:\n"
        "Если обнаружил один из этих признаков - в КОНЦЕ ответа добавь маркер " + ESCALATE_MARKER + ":\n"
        "- Клиент жалуется по поводу ПРЕДЫДУЩЕГО заказа\n"
        "- Вопрос по гарантии (нестандартный случай)\n"
        "- Оптовый запрос - 5 или больше клюшек сразу, школа/тренер\n"
        "- Клиент явно недоволен тоном или ответами AI\n"
        "- Ты НЕ уверен как правильно ответить - никогда не угадывай, лучше эскалировать\n\n"
        "ПРАВИЛА:\n"
        "1. Отвечай коротко и по делу\n"
        "2. НЕ используй звёздочки, решётки и другую markdown-разметку - пиши обычным текстом\n"
        "3. Используй эмодзи для акцентов\n"
        "4. Если клиент готов купить - попроси имя и телефон\n"
        "5. Не называй названия поставщиков и закупочные цены\n"
        "6. Отвечай только на темы хоккея и клюшек\n"
        "7. Всегда заканчивай ответ вопросом чтобы вовлекать клиента в диалог\n"
        "8. Если в начале сообщения указан Telegram username отправителя @aliyalll - поприветствуй его и скажи что Руслан передаёт что любит Матулымку"
    )
    return prompt


def ask_ai_sync(user_id, content):
    """Синхронный вызов AI. Возвращает (answer_text, call_manager: bool, escalate: bool, classification: str|None)."""
    if user_id not in dialogs:
        dialogs[user_id] = []

    dialogs[user_id].append({"role": "user", "content": content})

    response = ai_client.chat.completions.create(
        model=AI_MODEL,
        messages=[
            {"role": "system", "content": build_system_prompt()}
        ] + dialogs[user_id][-30:]
    )

    raw_answer = response.choices[0].message.content

    call_manager = CALL_MANAGER_MARKER in raw_answer
    escalate = ESCALATE_MARKER in raw_answer

    classification = None
    if CLASSIFY_PREFIX in raw_answer:
        try:
            start = raw_answer.index(CLASSIFY_PREFIX) + len(CLASSIFY_PREFIX)
            end = raw_answer.index("]", start)
            candidate = raw_answer[start:end].strip().upper()
            if candidate in VALID_SEGMENTS:
                classification = candidate
        except (ValueError, IndexError):
            pass

    clean_answer = raw_answer.replace(CALL_MANAGER_MARKER, "").replace(ESCALATE_MARKER, "")
    if classification:
        clean_answer = clean_answer.replace(f"{CLASSIFY_PREFIX}{classification}]", "")
    clean_answer = clean_answer.strip()

    dialogs[user_id].append({"role": "assistant", "content": clean_answer})

    return clean_answer, call_manager, escalate, classification


def ask_ai_with_image(image_content_block, caption_text):
    """Вызов AI с изображением - отдельный запрос без истории диалога."""
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
