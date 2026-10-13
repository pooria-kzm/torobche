"""Two-stage, LLM-assisted construction of comparison cards."""

import ast
import asyncio
import json
import os
import re
from pathlib import Path

from django.db import transaction

from .models import Car, CarCard

BASE_URL = os.environ.get("LLM_BASE_URL", "https://chatbot-llm-gateway.pr.mci.dev/v1")
API_KEY = os.environ.get("LLM_API_KEY", "")
DEFAULT_MODEL = os.environ.get("LLM_MODEL", "openai/gpt-oss-120b")
TRUSTED_SOURCES = {"hamrah", "bama", "karnameh", "khodro45"}
DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def tokenize_title(value):
    value = (value or "").translate(DIGITS).replace("ي", "ی").replace("ك", "ک").lower()
    # This is intentionally not a Hazm operation. Keep only Unicode letters
    # and numbers; punctuation (including Persian ،), spaces, ZWNJ, and all
    # other characters are discarded.
    return [char for char in value if char.isalnum()]


def title_key(value):
    return "".join(tokenize_title(value))


async def call_model(
    system_prompt: str, user_message: str, model: str = DEFAULT_MODEL, client=None
) -> str:
    from openai import AsyncOpenAI

    owned = client is None
    client = client or AsyncOpenAI(base_url=BASE_URL, api_key=API_KEY)
    request = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0,
    }
    # gpt-oss can spend the entire default completion budget on hidden
    # reasoning for a 400+ title catalog and return an empty content field.
    # Keep reasoning deliberately low and reserve enough output space for the
    # actual list. The gateway accepts these OpenAI-compatible parameters.
    if model.startswith("openai/gpt-oss"):
        request.update({"reasoning_effort": "low", "max_tokens": 20000})
    response = await client.chat.completions.create(**request)
    if owned:
        await client.close()
    return response.choices[0].message.content or ""


REDUCE_PROMPT = """
You are an expert automotive catalog normalization and deduplication system
with strong knowledge of car models, trims, engines, and Persian/Farsi and
English automotive terminology.

Your task is to transform a list of car names into a clean list of distinct,
valid, specific car variants.

Return ONLY a JSON array of strings, for example:
["پژو ۲۰۶ تیپ ۲", "پژو ۲۰۶ تیپ ۵"]

Follow these rules in order:

1. IDENTIFY VALID CAR VARIANTS
- Keep only real passenger vehicles and identifiable car variants.
- Remove advertisements, non-car titles, incomplete records, and entries
  that do not identify a sufficiently specific car variant.
- A make or model alone is not necessarily a valid variant.
- If a model has meaningful trim levels, require the trim when it is
  necessary to distinguish the variant.
- For example, remove "پژو ۲۰۶" if no trim is specified, because it could
  refer to multiple variants such as "پژو ۲۰۶ تیپ ۲" and
  "پژو ۲۰۶ تیپ ۶".
- Do not invent a trim, engine, transmission, or other specification
  that cannot be established from the input or reliable automotive knowledge.
- If a name is ambiguous and cannot be resolved confidently, remove it
  rather than guessing.

2. NORMALIZE PERSIAN, ENGLISH, AND NUMERICAL VARIATIONS
Recognize equivalent names despite differences in:
- Persian and English spelling.
- Persian, Arabic, and Western digits, such as ۲، ٢, and 2.
- Persian character variants, such as ي/ی and ك/ک.
- Spacing, punctuation, commas, hyphens, and word order.
- Persian transliterations of English model names and engine codes.
- Uppercase/lowercase differences and harmless spelling mistakes.
- Optional redundant words that do not change the vehicle's identity.

Use automotive knowledge and Persian language knowledge to identify
semantic equivalence, not just exact textual similarity.

Examples of equivalent names include:
- "پژو ، ۲۰۶ تیپ ۶" and "پژو ۲۰۶ تیپ 6".
- "پژو ۲۰۶ تیپ ۲" and "پژو 206 تیپ 2".
- "TU5" and "تیوفایو", when both refer to the same engine designation
  for the same vehicle variant.
- "پژو ۲۰۶ تیپ ۵" and "پژو ۲۰۶ تیپ پنج", when they identify the
  same variant.

These examples illustrate normalization, not permission to merge
different vehicle variants.

3. MERGE ONLY IDENTICAL VARIANTS
- Merge entries only when they refer to the same actual vehicle variant.
- Preserve meaningful distinctions in make, model, generation, body style,
  trim, engine, fuel type, transmission, drivetrain, and other specifications
  when these distinguish actual variants in the catalog.
- In particular, Peugeot 206 Tip 2, Tip 5, and Tip 6 are different variants
  and MUST remain separate.
- Never merge different trims into a generic model name.
- Never assume two engine codes, trim names, or model designations are
  equivalent merely because they appear similar.
- A shared model name does not make two entries duplicates.
- When uncertain whether two names represent the same variant, do not merge
  them unless equivalence can be established confidently.

4. CHOOSE ONE CANONICAL NAME PER VARIANT
- Select one consistent, concise, recognizable name for each valid variant.
- Prefer standard automotive naming conventions commonly used in Persian
  car catalogs.
- Use Persian names for Persian-market vehicles when that is the clearest
  conventional form; preserve established Latin engine codes and model
  designations where appropriate, such as TU5.
- Express trim numbers consistently using Western digits in the canonical
  name, for example "پژو ۲۰۶ تیپ 6" or another single consistent format
  throughout the output.
- Do not include multiple spellings of the same variant.
- Do not include sales language, location, mileage, price, model year,
  condition, seller information, or advertising text unless a year or
  specification is essential to distinguish the actual variant.
- Do not add specifications simply to make a name look more detailed.

5. FINAL VALIDATION
Before returning the result, verify that:
- Every entry is a valid and sufficiently specific car variant.
- No two entries refer to the same variant under different spellings.
- Distinct trims and other meaningful variants remain separate.
- Generic or unresolved names have been removed.
- Every output name is concise and canonical.
- The output contains no explanations, comments, or extra keys.

Return ONLY the JSON array. Do not return an object, explanation, markdown, or reasoning.
"""


CLASSIFY_PROMPT = """You classify marketplace listings into the supplied fixed car cards.
Return ONLY valid JSON: {"assignments":[{"car_id":123,"card_title":"...","is_car":true}]}.
Return exactly one assignment for every car_id. Use only a card_title copied exactly from
the supplied cards. Use is_car=false and card_title=null for non-cars or listings you
cannot reliably identify as a car; those must be ignored.
Use automotive knowledge and read messy Persian/English intelligently. Strip ad noise:
"پژو ۲۰۶ تیپ ۲ فروش فوری" belongs to "پژو ۲۰۶ تیپ ۲". Interpret "پژو ۲۰۶ وی هشت موتور
تیوفایو" as Peugeot 206 V8; "پژو 206 تیپ 2 مدل 1400 tu3 درحد با رینگ 207 فوری" belongs
to Peugeot 206 Tip 2. Preserve specificity: never assign Tip 2 or Tip 5 to a generic
Peugeot 206 card if a specific card exists. Divar and Sheypoor may be junk, e.g.
"اسقاطی ماشین فرسوده بالاترین قیمت"; ignore such listings."""


def _json(raw, key):
    """Parse a response list, accepting a fenced/list/object compatibility form."""
    raw = re.sub(
        r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip(), flags=re.IGNORECASE | re.DOTALL
    )
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        try:
            data = ast.literal_eval(raw)
        except (SyntaxError, ValueError):
            match = re.search(r"\[[\s\S]*\]", raw)
            if not match:
                return []
            try:
                data = json.loads(match.group(0))
            except (TypeError, ValueError):
                return []
    value = data.get(key, []) if isinstance(data, dict) else data
    return value if isinstance(value, list) else []


def _clean(value, fallback=""):
    value = (value or "").translate(DIGITS).replace("ي", "ی").replace("ك", "ک").lower()
    cleaned = "".join(char if char.isalnum() else " " for char in value)
    result = " ".join(cleaned.split())[:255]
    if result or not fallback:
        return result
    return _clean(fallback)


def _car_rows(queryset):
    return [
        {
            "id": car.pk,
            "title": car.title,
            "source": car.source,
            "image_url": car.image_url,
        }
        for car in queryset.order_by("pk")
    ]


def extract_unique_titles(queryset=None):
    """Exact-deduplicate trusted-site titles before the reduction request."""
    rows = _car_rows(queryset or Car.objects.filter(is_active=True))
    unique = {}
    trusted_count = 0
    for row in rows:
        if row["source"] in TRUSTED_SOURCES:
            trusted_count += 1
            cleaned = _clean(row["title"])
            unique.setdefault(title_key(row["title"]), cleaned)
    return list(unique.values()), len(rows), trusted_count


def _read_titles(path):
    return [item["title"] for item in _read_cards(path)]


def _read_cards(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    titles = data.get("cards", data.get("titles", data)) if isinstance(data, dict) else data
    if not isinstance(titles, list):
        raise TypeError('card file must contain a JSON list or {"cards": [...]}')
    cards, seen = [], set()
    for item in titles:
        if isinstance(item, str):
            title, description = item, ""
        elif isinstance(item, dict):
            title = item.get("title", item.get("name", ""))
            description = item.get("describtion", item.get("description", "")) or ""
        else:
            continue
        title = _clean(title)
        if title and title_key(title) not in seen:
            seen.add(title_key(title))
            cards.append({"title": title, "describtion": str(description)[:10000]})
    return cards


async def _reduce_titles(unique_titles, model):
    from openai import AsyncOpenAI

    client = AsyncOpenAI(base_url=BASE_URL, api_key=API_KEY)
    text = "\n".join(f"{i + 1}. {title}" for i, title in enumerate(unique_titles))
    try:
        raw = ""
        parsed = []
        for attempt in range(2):
            request_text = (
                text
                if attempt == 0
                else (
                    text + "\n\nIMPORTANT: your previous response was empty or invalid. "
                    "Return the canonical JSON array now, with at least one string."
                )
            )
            raw = await call_model(REDUCE_PROMPT, request_text, model=model, client=client)
            parsed = [_clean(item) for item in _json(raw, "cards") if isinstance(item, str)]
            # A large request occasionally returns [] or a trivial one-item
            # answer after exhausting reasoning. Treat that as failure rather
            # than silently replacing a 400-title catalog with one card.
            if parsed and (len(unique_titles) <= 2 or len(parsed) > 1):
                break
    finally:
        await client.close()
    reduced = list(dict.fromkeys(item for item in parsed if item))
    return (reduced or unique_titles), len(reduced), not bool(reduced), raw


def extract_card_titles(output_path, model=DEFAULT_MODEL, queryset=None, progress=None):
    """Run the first LLM call and save canonical card names to JSON."""
    progress = progress or (lambda message: None)
    unique, car_count, trusted_count = extract_unique_titles(queryset)
    progress(
        f"Found {car_count} active cars, {trusted_count} trusted listings, "
        f"and {len(unique)} unique trusted-site titles after exact normalization."
    )
    if not unique:
        titles = []
        progress("No trusted-site titles found; writing an empty card file.")
    else:
        progress(f"Calling title-reduction LLM with {len(unique)} titles...")
        titles, parsed_count, used_fallback, raw_response = asyncio.run(
            _reduce_titles(unique, model)
        )
        progress(f"Reduction response received: {len(raw_response)} characters.")
        progress(f"Reduction response starts with: {raw_response[:180].replace(chr(10), ' ')}")
        if used_fallback:
            progress("WARNING: LLM response had no parseable cards; kept normalized titles.")
        else:
            progress(
                f"LLM returned {parsed_count} parseable cards; saved {len(titles)} unique cards."
            )
    payload = {"title": model, "input_unique_titles": len(unique), "cards": titles}
    Path(output_path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    progress(f"Saved card title file: {output_path}")
    return {
        "cars": car_count,
        "unique": len(unique),
        "cards": len(titles),
        "path": str(output_path),
    }


async def _classify_batches(card_titles, batches, model, progress):
    from openai import AsyncOpenAI

    client = AsyncOpenAI(base_url=BASE_URL, api_key=API_KEY)
    card_text = "\n".join(f"- {title}" for title in card_titles) or "(no cards)"

    async def classify(number, batch):
        listings = "\n".join(f"{row['id']}: {row['title']}" for row in batch)
        raw = await call_model(
            CLASSIFY_PROMPT,
            f"Fixed cards:\n{card_text}\n\nListings:\n{listings}",
            model=model,
            client=client,
        )
        return number, _json(raw, "assignments")

    tasks = [asyncio.create_task(classify(i + 1, batch)) for i, batch in enumerate(batches)]
    results = []
    try:
        for future in asyncio.as_completed(tasks):
            number, assignments = await future
            results.extend(assignments)
            progress(
                f"Finished batch {number}/{len(batches)} ({len(assignments)} assignments returned)."
            )
    finally:
        await client.close()
    return results


def classify_car_cards(
    card_file, batch_size=100, model=DEFAULT_MODEL, queryset=None, progress=None
):
    """Load card titles and classify every active car in fixed-size batches."""
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    progress = progress or (lambda message: None)
    card_records = _read_cards(card_file)
    card_titles = [item["title"] for item in card_records]
    rows = _car_rows(queryset or Car.objects.filter(is_active=True))
    batches = [rows[i : i + batch_size] for i in range(0, len(rows), batch_size)]
    progress(f"Loaded {len(card_titles)} card titles from {card_file}.")
    progress(f"Loaded {len(rows)} cars; sending {len(batches)} batches of up to {batch_size}.")
    assignments = (
        asyncio.run(_classify_batches(card_titles, batches, model, progress)) if batches else []
    )
    with transaction.atomic():
        existing = {title_key(card.title): card for card in CarCard.objects.all()}
        cards, created = {}, 0
        descriptions = {title_key(item["title"]): item["describtion"] for item in card_records}
        for title in card_titles:
            key = title_key(title)
            card = existing.get(key) or CarCard.objects.create(title=title)
            if card.describtion != descriptions.get(key, ""):
                card.describtion = descriptions.get(key, "")
                card.save(update_fields=["describtion", "updated_at"])
            created += int(key not in existing)
            cards[key] = card
        by_id = {row["id"]: row for row in rows}
        assigned = 0
        for item in assignments:
            if not isinstance(item, dict) or item.get("is_car") is False:
                continue
            try:
                row = by_id[int(item["car_id"])]
            except (KeyError, TypeError, ValueError):
                continue
            card = cards.get(title_key(item.get("card_title")))
            if card is None:
                continue
            card.cars.add(row["id"])
            assigned += 1
            if not card.image_url and row["image_url"]:
                card.image_url = row["image_url"]
                card.save(update_fields=["image_url", "updated_at"])
    progress(f"Saved {assigned} assignments and {created} new cards.")
    return {
        "cars": len(rows),
        "batches": len(batches),
        "created": created,
        "assigned": assigned,
    }


def process_car_cards(
    batch_size=100,
    model=DEFAULT_MODEL,
    queryset=None,
    progress=None,
    card_file="car_card_titles.json",
):
    """Backward-compatible combined operation used by the crawler."""
    return classify_car_cards(
        card_file,
        batch_size=batch_size,
        model=model,
        queryset=queryset,
        progress=progress,
    )
