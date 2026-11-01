import re
from .security import fail

CATALOG = [
    {
        "id": "soundcore-q30",
        "name": "Soundcore Life Q30",
        "type": "headphones",
        "amount": 800000,
        "currency": "RUB",
        "merchant": "Soundstore",
        "category": "electronics",
        "details": "Беспроводные · ANC · 40 часов",
        "color": "#d5ddd8",
    },
    {
        "id": "sony-ch720",
        "name": "Sony WH-CH720N",
        "type": "headphones",
        "amount": 1200000,
        "currency": "RUB",
        "merchant": "Soundstore",
        "category": "electronics",
        "details": "Беспроводные · ANC · 35 часов",
        "color": "#e6dfcf",
    },
    {
        "id": "marshall-major",
        "name": "Marshall Major V",
        "type": "headphones",
        "amount": 1800000,
        "currency": "RUB",
        "merchant": "Audio Market",
        "category": "electronics",
        "details": "Беспроводные · 100 часов",
        "color": "#d9d5e6",
    },
    {
        "id": "logitech-mx",
        "name": "Logitech MX Anywhere",
        "type": "mouse",
        "amount": 750000,
        "currency": "RUB",
        "merchant": "Tech Market",
        "category": "electronics",
        "details": "Беспроводная мышь · Bluetooth",
        "color": "#dddfe8",
    },
]


def interpret(prompt):
    text = prompt.lower().replace("\u00a0", " ")
    kind = (
        "headphones"
        if any(
            x in text for x in ["науш", "headphone", "sony", "marshall", "soundcore"]
        )
        else "mouse"
        if any(x in text for x in ["мыш", "mouse", "logitech"])
        else None
    )
    if not kind:
        fail(
            422,
            "INTENT_UNCLEAR",
            "Укажите наушники или мышь и бюджет. Например: «Купи наушники до 12 000 рублей».",
        )
    matches = re.findall(
        r"(\d[\d\s]*(?:[.,]\d{1,2})?)\s*(тыс(?:яч)?|k)?\s*(?:руб|₽|р\b)?", text
    )
    if not matches:
        fail(422, "BUDGET_REQUIRED", "Укажите бюджет в рублях")
    try:
        raw, suffix = matches[-1]
        amount = int(
            float(raw.replace(" ", "").replace(",", "."))
            * (1000 if suffix else 1)
            * 100
        )
    except ValueError:
        fail(422, "BUDGET_REQUIRED", "Не удалось прочитать бюджет")
    products = [x for x in CATALOG if x["type"] == kind and x["amount"] <= amount]
    if not products:
        fail(422, "NO_CATALOG_MATCH", "В каталоге нет товара в пределах этого бюджета")
    # Deterministic demonstration parser, not an LLM; choose best catalog item within budget.
    return max(products, key=lambda x: x["amount"]), amount
