import base64
import csv
import json
import os
import re
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware


ROOT = Path(__file__).resolve().parent
SEED_PATH = ROOT.parent / "supabase" / "seed_wines.csv"

app = FastAPI(title="Aislewise API", version="0.1.0")

allowed_origins = [
    origin.strip()
    for origin in os.getenv("ALLOWED_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/recommend")
async def recommend(
    budget: str = Form("$20"),
    food: str = Form("Steak"),
    occasion: str = Form("Dinner party"),
    photo: UploadFile | None = File(None),
) -> dict[str, Any]:
    wines = await load_wines()
    extracted: list[dict[str, Any]] = []
    warnings: list[str] = []
    scan_debug = scan_debug_info(photo)

    try:
        extracted = await extract_wines_from_photo(photo)
    except Exception as exc:
        warnings.append("Photo analysis did not finish, so starter recommendations were used.")
        print(f"vision_extraction_failed: {type(exc).__name__}: {exc}")

    if photo and not os.getenv("OPENAI_API_KEY"):
        warnings.append("Photo was received, but OpenAI vision is not configured on the API.")
    elif photo and not extracted and not warnings:
        warnings.append("Photo was received, but no wine label was extracted. Starter recommendations were used.")

    print(
        "scan_debug: "
        f"has_photo={scan_debug['has_photo']} "
        f"filename={scan_debug['filename']} "
        f"content_type={scan_debug['content_type']} "
        f"size={scan_debug['size']} "
        f"vision_configured={scan_debug['vision_configured']} "
        f"extracted_count={len(extracted)}"
    )
    if extracted:
        print(f"vision_extracted: {json.dumps(extracted[:3], ensure_ascii=True)}")

    candidates = match_detected_wines(extracted, wines)

    if extracted and not candidates:
        candidates = unmatched_detected_wines(extracted)
        warnings.append(
            "Photo analysis found a wine, but it is not in the starter database yet."
        )
    elif not candidates:
        candidates = visible_demo_wines(wines)

    recommendations = rank_wines(candidates, budget, food, occasion)
    return {
        "budget": budget,
        "food": food,
        "occasion": occasion,
        "detected_wines": candidates,
        "recommendations": recommendations[:2],
        "source": response_source(extracted, candidates),
        "warnings": warnings,
        "debug": scan_debug,
    }


async def load_wines() -> list[dict[str, Any]]:
    try:
        remote = await load_wines_from_supabase()
    except Exception as exc:
        print(f"supabase_load_failed: {type(exc).__name__}: {exc}")
        remote = []

    if remote:
        return [normalize_wine(row) for row in remote]

    with SEED_PATH.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return [normalize_wine(row) for row in rows]


async def load_wines_from_supabase() -> list[dict[str, Any]]:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        return []

    endpoint = f"{supabase_rest_base(url)}/wines"
    headers = {
        "apikey": key,
        "authorization": f"Bearer {key}",
    }
    params = {
        "select": "*",
        "limit": "3000",
    }

    async with httpx.AsyncClient(timeout=12) as client:
        response = await client.get(endpoint, headers=headers, params=params)
        response.raise_for_status()
        return response.json()


async def extract_wines_from_photo(photo: UploadFile | None) -> list[dict[str, Any]]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or not photo:
        return []

    image_bytes = await photo.read()
    if not image_bytes:
        return []

    content_type = photo.content_type or "image/jpeg"
    data_url = f"data:{content_type};base64,{base64.b64encode(image_bytes).decode('utf-8')}"
    prompt = (
        "Extract wines visible in this shelf photo. Return strict JSON with a "
        "'wines' array. Each item should include display_name, producer, varietal, "
        "vintage, price, and confidence from 0 to 1. Use null when unknown."
    )

    payload = {
        "model": os.getenv("OPENAI_VISION_MODEL", "gpt-5-mini"),
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {"type": "input_image", "image_url": data_url},
                ],
            }
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "wine_shelf_extraction",
                "strict": True,
                "schema": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "wines": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "display_name": {"type": ["string", "null"]},
                                    "producer": {"type": ["string", "null"]},
                                    "varietal": {"type": ["string", "null"]},
                                    "vintage": {"type": ["string", "null"]},
                                    "price": {"type": ["number", "null"]},
                                    "confidence": {"type": "number"},
                                },
                                "required": [
                                    "display_name",
                                    "producer",
                                    "varietal",
                                    "vintage",
                                    "price",
                                    "confidence",
                                ],
                            },
                        }
                    },
                    "required": ["wines"],
                },
            }
        },
    }

    async with httpx.AsyncClient(timeout=35) as client:
        response = await client.post(
            "https://api.openai.com/v1/responses",
            headers={
                "authorization": f"Bearer {api_key}",
                "content-type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        body = response.json()

    text = collect_response_text(body)
    if not text:
        return []

    parsed = json.loads(text)
    return parsed.get("wines", [])


def scan_debug_info(photo: UploadFile | None) -> dict[str, Any]:
    return {
        "has_photo": photo is not None,
        "filename": photo.filename if photo else None,
        "content_type": photo.content_type if photo else None,
        "size": photo.size if photo else None,
        "vision_configured": bool(os.getenv("OPENAI_API_KEY")),
    }


def collect_response_text(body: dict[str, Any]) -> str:
    chunks: list[str] = []
    for item in body.get("output", []):
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                chunks.append(content["text"])
    return "".join(chunks)


def match_detected_wines(
    extracted: list[dict[str, Any]], wines: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    if not extracted:
        return []

    matches: list[dict[str, Any]] = []
    seen: set[str] = set()

    for item in extracted:
        query = " ".join(
            str(item.get(key) or "")
            for key in ("display_name", "name", "producer", "varietal")
        )
        normalized_query = normalize_text(query)
        if not normalized_query:
            continue

        best = None
        best_score = 0
        for wine in wines:
            score = token_overlap(normalized_query, wine["search_text"])
            if score > best_score:
                best = wine
                best_score = score

        if best and best_score >= 0.25 and best["id"] not in seen:
            merged = {**best}
            if item.get("price"):
                merged["price"] = coerce_float(item.get("price"))
            merged["recognition_confidence"] = item.get("confidence") or best_score
            matches.append(merged)
            seen.add(best["id"])

    return matches


def unmatched_detected_wines(extracted: list[dict[str, Any]]) -> list[dict[str, Any]]:
    wines: list[dict[str, Any]] = []
    for index, item in enumerate(extracted):
        display_name = (
            item.get("display_name")
            or item.get("name")
            or item.get("producer")
            or "Detected wine"
        )
        varietal = item.get("varietal") or "Wine"
        price = coerce_float(item.get("price"))
        confidence = coerce_float(item.get("confidence")) or 0.55
        wines.append(
            {
                "id": f"unmatched-{index + 1}",
                "display_name": display_name,
                "producer": item.get("producer"),
                "normalized_name": normalize_text(display_name),
                "aliases": [],
                "varietal": varietal,
                "region": None,
                "country": None,
                "avg_price": price,
                "price": price,
                "price_band": None,
                "rating_estimate": 3.7,
                "pairing_tags": inferred_pairing_tags(varietal),
                "occasion_tags": ["weeknight"],
                "style": "Detected from your photo, but not yet in the starter wine database",
                "crowd_pleaser_score": 6,
                "value_score": 5,
                "known_retailers": [],
                "label_keywords": [],
                "recognition_confidence": confidence,
                "search_text": normalize_text(f"{display_name} {item.get('producer') or ''} {varietal}"),
                "unmatched": True,
            }
        )
    return wines


def response_source(extracted: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> str:
    if extracted and any(candidate.get("unmatched") for candidate in candidates):
        return "openai_vision_unmatched"
    if extracted:
        return "openai_vision"
    return "demo_or_seed"


def visible_demo_wines(wines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    preferred = [
        "kirkland signature rioja reserva",
        "decoy cabernet sauvignon",
        "la crema pinot noir",
    ]
    selected: list[dict[str, Any]] = []
    for target in preferred:
        match = next((wine for wine in wines if target in wine["search_text"]), None)
        if match:
            selected.append(match)
    return selected or wines[:3]


def rank_wines(
    candidates: list[dict[str, Any]], budget: str, food: str, occasion: str
) -> list[dict[str, Any]]:
    max_budget = parse_budget(budget)
    ranked: list[dict[str, Any]] = []

    for wine in candidates:
        price = wine.get("price") or wine.get("avg_price") or 0
        budget_fit = 1.0 if price <= max_budget else max(0.0, 1 - ((price - max_budget) / max_budget))
        pairing_fit = tag_match(food, wine.get("pairing_tags", []))
        occasion_fit = tag_match(occasion, wine.get("occasion_tags", []))
        value_fit = normalized_score(wine.get("value_score"), 10)
        rating_fit = normalized_score(wine.get("rating_estimate"), 5)
        recognition = float(wine.get("recognition_confidence") or 0.85)

        score = (
            budget_fit * 30
            + pairing_fit * 25
            + occasion_fit * 15
            + ((value_fit * 0.55) + (rating_fit * 0.45)) * 20
            + recognition * 10
        )

        ranked.append(
            {
                **wine,
                "score": round(score),
                "badge": badge_for(wine, score, budget_fit),
                "confidence_label": confidence_label(recognition, score),
                "reasons": reasons_for(wine, budget, food, occasion, budget_fit),
            }
        )

    return sorted(ranked, key=lambda item: item["score"], reverse=True)


def reasons_for(
    wine: dict[str, Any], budget: str, food: str, occasion: str, budget_fit: float
) -> list[str]:
    reasons = []
    if budget_fit >= 1:
        reasons.append(f"Fits your {budget} budget")
    else:
        reasons.append(f"Slightly above {budget}, but still a strong match")

    if tag_match(food, wine.get("pairing_tags", [])) > 0:
        reasons.append(f"Good match for {food.lower()}")
    else:
        reasons.append(f"More about style and value than the {food.lower()} pairing")

    if tag_match(occasion, wine.get("occasion_tags", [])) > 0:
        reasons.append(f"Works for {occasion.lower()}")
    else:
        reasons.append("Useful backup if you want something different")

    if wine.get("style"):
        reasons.append(str(wine["style"]))

    return reasons[:4]


def normalize_wine(row: dict[str, Any]) -> dict[str, Any]:
    aliases = parse_list(row.get("aliases"))
    pairing_tags = parse_list(row.get("pairing_tags"))
    occasion_tags = parse_list(row.get("occasion_tags"))
    known_retailers = parse_list(row.get("known_retailers"))
    label_keywords = parse_list(row.get("label_keywords"))
    display_name = row.get("display_name") or row.get("wine_name") or ""
    producer = row.get("producer") or ""
    varietal = row.get("varietal") or ""
    pairing_tags = pairing_tags or inferred_pairing_tags(varietal)
    occasion_tags = occasion_tags or inferred_occasion_tags(row)

    search_text = normalize_text(
        " ".join([display_name, producer, varietal, " ".join(aliases), " ".join(label_keywords)])
    )

    return {
        "id": str(row.get("id") or normalize_text(display_name).replace(" ", "-")),
        "display_name": display_name,
        "producer": producer,
        "normalized_name": row.get("normalized_name") or normalize_text(display_name),
        "aliases": aliases,
        "varietal": varietal,
        "region": row.get("region"),
        "country": row.get("country"),
        "avg_price": coerce_float(row.get("avg_price")),
        "price": coerce_float(row.get("price") or row.get("avg_price")),
        "price_band": row.get("price_band"),
        "rating_estimate": coerce_float(row.get("rating_estimate")),
        "pairing_tags": pairing_tags,
        "occasion_tags": occasion_tags,
        "style": row.get("style"),
        "crowd_pleaser_score": coerce_float(row.get("crowd_pleaser_score")),
        "value_score": coerce_float(row.get("value_score")),
        "known_retailers": known_retailers,
        "label_keywords": label_keywords,
        "search_text": search_text,
    }


def parse_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [item.strip() for item in str(value).split(",") if item.strip()]


def supabase_rest_base(url: str) -> str:
    base = url.rstrip("/")
    if base.endswith("/rest/v1"):
        return base
    return f"{base}/rest/v1"


def coerce_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace("$", "").strip())
    except ValueError:
        return None


def normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", value.lower()).strip()


def token_overlap(query: str, target: str) -> float:
    query_tokens = set(query.split())
    target_tokens = set(target.split())
    if not query_tokens or not target_tokens:
        return 0
    return len(query_tokens & target_tokens) / len(query_tokens)


def parse_budget(budget: str) -> float:
    numbers = re.findall(r"\d+", budget)
    return float(numbers[0]) if numbers else 20.0


def tag_match(value: str, tags: list[str]) -> float:
    normalized = normalize_text(value)
    normalized_tags = {normalize_text(tag) for tag in tags}
    if normalized in {"", "none"}:
        return 0.5
    return 1.0 if normalized in normalized_tags else 0.0


def inferred_pairing_tags(varietal: str) -> list[str]:
    key = normalize_text(varietal)
    defaults = {
        "cabernet sauvignon": ["steak", "burgers", "pasta", "grilled food"],
        "tempranillo": ["steak", "burgers", "tapas", "grilled food"],
        "pinot noir": ["chicken", "salmon", "mushrooms", "cheese"],
        "zinfandel": ["burgers", "bbq", "pizza", "grilled food"],
        "malbec": ["steak", "burgers", "bbq", "grilled food"],
        "red blend": ["burgers", "bbq", "pizza", "pasta"],
        "sauvignon blanc": ["seafood", "chicken", "cheese"],
        "chardonnay": ["chicken", "pasta", "seafood", "cheese"],
        "riesling": ["seafood", "spicy food", "chicken"],
        "gamay": ["chicken", "cheese", "pasta"],
    }
    return defaults.get(key, [])


def inferred_occasion_tags(row: dict[str, Any]) -> list[str]:
    tags = ["weeknight"]
    price = coerce_float(row.get("avg_price") or row.get("price")) or 0
    crowd = coerce_float(row.get("crowd_pleaser_score")) or 0
    value = coerce_float(row.get("value_score")) or 0

    if price <= 15 or value >= 8:
        tags.append("value")
    if crowd >= 8:
        tags.extend(["dinner party", "safe pick"])
    if price >= 18:
        tags.extend(["gift", "date night"])
    return list(dict.fromkeys(tags))


def normalized_score(value: Any, max_value: float) -> float:
    number = coerce_float(value) or 0
    return min(max(number / max_value, 0), 1)


def badge_for(wine: dict[str, Any], score: float, budget_fit: float) -> str:
    if budget_fit < 1:
        return "Over Budget"
    if (wine.get("value_score") or 0) >= 8:
        return "Best Value"
    if score >= 85:
        return "Safer Pick"
    return "Good Fit"


def confidence_label(recognition: float, score: float) -> str:
    if recognition >= 0.85 and score >= 85:
        return "High confidence"
    if recognition >= 0.65:
        return "Medium-high confidence"
    return "Lower confidence"
