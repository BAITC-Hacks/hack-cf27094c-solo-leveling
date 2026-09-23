"Deterministic filtering, ranking, and source-grounded explanations."

from __future__ import annotations

from collections import Counter
from datetime import date
import math
import re

from catalog import CALENDAR_END, CALENDAR_START, CATALOG, Contractor


WORDS = re.compile(r"[а-яёa-z0-9]{4,}", re.IGNORECASE)
COMMON = frozenset(
    "которые который также более очень ваши наших можно своих работа работаем "
    "мероприятия мероприятий свадьбы свадебные каждого каждый всегда профессиональный "
    "команда алматы астаны клиентов гостей атмосфера".split()
)
DOCUMENT_FREQUENCY = Counter(
    word for item in CATALOG for word in set(WORDS.findall(item.description.lower()))
)


class InvalidQuery(ValueError):
    pass


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]+", str(value)):
        raise InvalidQuery(f"{field}: укажите положительное целое число")
    number = int(value)
    if number <= 0:
        raise InvalidQuery(f"{field}: укажите положительное целое число")
    return number


def _plural(number: int, one: str, few: str, many: str) -> str:
    if number % 10 == 1 and number % 100 != 11:
        return one
    if 2 <= number % 10 <= 4 and not 12 <= number % 100 <= 14:
        return few
    return many


def validate(raw: dict) -> dict:
    required = ("city", "event_date", "event_format", "category", "budget")
    if any(not str(raw.get(key, "")).strip() for key in required):
        raise InvalidQuery("Заполните город, дату, формат, категорию и бюджет")
    try:
        event_date = date.fromisoformat(str(raw["event_date"]))
    except (TypeError, ValueError):
        raise InvalidQuery("Дата должна быть в формате ГГГГ-ММ-ДД") from None
    if not date.fromisoformat(CALENDAR_START) <= event_date <= date.fromisoformat(CALENDAR_END):
        raise InvalidQuery(f"Календарь доступен с {CALENDAR_START} по {CALENDAR_END}")
    hours = raw.get("hours")
    return {
        "city": str(raw["city"]).strip(),
        "event_date": event_date.isoformat(),
        "event_format": str(raw["event_format"]).strip(),
        "category": str(raw["category"]).strip(),
        "budget": _positive_int(raw["budget"], "Бюджет"),
        "hours": _positive_int(hours, "Длительность") if hours not in (None, "") else None,
        "language": str(raw.get("language") or "").strip(),
        "wishes": str(raw.get("wishes") or "").strip()[:120],
    }


def _snippets(description: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+|[;\n•]+", description)
    snippets = []
    for part in parts:
        part = " ".join(part.strip(" -–—.,!?").split())
        if len(part) < 22:
            continue
        if len(part) > 175:
            part = part[:175].rsplit(" ", 1)[0].rstrip(" ,.;:") + "…"
        snippets.append(part)
    return snippets or [" ".join(description[:165].split()).rstrip(" ,.;:") + "…"]


def _evidence(item: Contractor, query: dict) -> tuple[float, str]:
    wishes = set(WORDS.findall(query["wishes"].lower())) - COMMON
    fmt = set(WORDS.findall(query["event_format"].lower()))

    def measure(snippet: str) -> float:
        words = set(WORDS.findall(snippet.lower())) - COMMON
        overlap = len(words & wishes)
        relevant_format = len(words & fmt)
        rare = sum(math.log((1 + len(CATALOG)) / (1 + DOCUMENT_FREQUENCY[w])) for w in words)
        # Prefer a concrete, readable source excerpt; user wishes get priority.
        return overlap * 12 + relevant_format * 3 + min(rare, 28) / 5 + min(len(snippet), 100) / 100

    snippet = max(_snippets(item.description), key=lambda text: (measure(text), -len(text), text))
    return measure(snippet), snippet.rstrip(".!?…") + ("…" if snippet.endswith("…") else "")


def _card(item: Contractor, query: dict) -> tuple[float, dict]:
    evidence_score, excerpt = _evidence(item, query)
    budget = query["budget"]
    price = item.price
    details = [
        f"На {query['event_date']} доступен",
        f"берёт формат «{query['event_format']}»",
        f"цена от {price:,} ₸ укладывается в бюджет {budget:,} ₸".replace(",", " "),
    ]
    if query["language"]:
        details.append(f"работает на языке «{query['language']}»")
    if query["hours"] is not None and item.max_hours is not None:
        details.append(f"может работать до {item.max_hours} ч при запросе {query['hours']} ч")
    explanation = "; ".join(details) + f". В описании: «{excerpt}»."
    score = evidence_score + 2 * (1 - price / budget)
    return score, {
        "id": item.id,
        "name": item.name,
        "categories": sorted(item.categories),
        "city": item.city,
        "price_from_kzt": price,
        "synthetic": item.synthetic,
        "city_imputed": item.city_imputed,
        "price_imputed": item.price_imputed,
        "explanation": explanation,
    }


def recommend(raw: dict, catalog: tuple[Contractor, ...] = CATALOG) -> dict:
    query = validate(raw)
    subset = [p for p in catalog if p.city == query["city"] and query["category"] in p.categories]
    counts = {"city_category": len(subset), "busy": 0, "over_budget": 0,
              "wrong_format": 0, "too_short": 0, "wrong_language": 0}
    if not subset:
        return {"status": "no_category", "cards": [], "counts": counts,
                "message": f"В городе {query['city']} нет подрядчиков категории «{query['category']}»."}

    eligible = []
    for item in subset:
        if query["event_date"] in item.busy_dates:
            counts["busy"] += 1
        elif item.price > query["budget"]:
            counts["over_budget"] += 1
        elif query["event_format"] not in item.formats:
            counts["wrong_format"] += 1
        elif query["hours"] is not None and item.max_hours is not None and item.max_hours < query["hours"]:
            counts["too_short"] += 1
        elif query["language"] and query["language"] not in item.languages:
            counts["wrong_language"] += 1
        else:
            eligible.append(item)

    labels = (("busy", "занят на дату", "заняты на дату"),
              ("over_budget", "дороже бюджета", "дороже бюджета"),
              ("wrong_format", "не берёт формат", "не берут формат"),
              ("too_short", "не хватает часов", "не хватает часов"),
              ("wrong_language", "не работает на нужном языке", "не работают на нужном языке"))
    exclusions = ", ".join(
        f"{counts[key]} {_plural(counts[key], one, many, many)}"
        for key, one, many in labels if counts[key]
    )
    ranked = sorted((_card(item, query) for item in eligible), key=lambda pair: (-pair[0], pair[1]["id"]))
    cards = [card for _, card in ranked[:3]]
    if not cards:
        status = "no_eligible"
        message = (f"В городе есть {len(subset)} "
                   f"{_plural(len(subset), 'профиль', 'профиля', 'профилей')} "
                   f"категории «{query['category']}», но ни один не прошёл условия: {exclusions}.")
    else:
        status = "matched"
        message = (f"Подобрано {len(cards)} из {len(eligible)} "
                   f"{_plural(len(eligible), 'подходящего профиля', 'подходящих профилей', 'подходящих профилей')}.")
        if len(cards) < 3:
            message += f" Меньше трёх: в каталоге этой категории {len(subset)}; {exclusions or 'других профилей нет'}."
        elif exclusions:
            message += f" Исключены другие профили: {exclusions}."
    return {"status": status, "cards": cards, "counts": counts, "message": message}
