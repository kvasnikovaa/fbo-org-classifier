# classifier_core.py

import re
from collections import Counter
from typing import Dict, Tuple, Any, List, Optional

import requests
from bs4 import BeautifulSoup


# ---------- Keyword configs ----------

RELIGION_KEYWORDS: Dict[str, List[str]] = {
    "Islam": [
        "mosque", "masjid", "islamic", "muslim", "ummah",
        "zakat", "sadaqa", "sadaqah", "waqf", "ramadan",
        "eid", "qurbani", "udhiyah", "fidyah", "kaffarah"
    ],
    "Christianity": [
        "church", "parish", "diocese", "cathedral", "chapel",
        "ministry", "ministries", "christian", "catholic",
        "orthodox", "baptist", "lutheran", "pentecostal",
        "evangelical", "jesus", "christ", "gospel"
    ],
    "Judaism": [
        "synagogue", "shul", "yeshiva", "yeshivah", "temple",
        "jewish", "judaism", "tzedakah", "tzedaka", "tzedokah",
        "maaser", "ma'aser", "high holidays", "rosh hashanah",
        "yom kippur", "sukkot", "simchat torah"
    ],
    # отдельная религия для interfaith/multi-faith
    "Multi-faith": [
        "interfaith", "inter faith", "inter-faith",
        "multi-faith", "multi faith",
        "inter faith network", "multi-faith network"
    ],
}

GENERIC_FAITH_KEYWORDS: List[str] = [
    "faith-based", "faith based", "religious organization",
    "religious non-profit", "religious nonprofit",
    "worship", "spiritual community", "congregation",
    "house of worship", "faith communities", "faith community"
]

WORSHIP_PLACE_KEYWORDS: List[str] = [
    "church", "parish", "diocese", "cathedral", "chapel",
    "mosque", "masjid", "synagogue", "shul", "temple",
    "congregation", "house of worship"
]

WORSHIP_PRACTICE_KEYWORDS: List[str] = [
    "worship service", "worship services", "sunday service",
    "mass", "liturgy", "prayer service", "daily prayers",
    "friday prayer", "jummah", "shabbat", "shabbos"
]

GLOBAL_NGO_KEYWORDS: List[str] = [
    "relief", "foundation", "international", "global",
    "aid", "charity", "humanitarian", "development",
    "mission", "missions", "ministries", "ngo", "non-profit",
    "nonprofit", "organisation", "organization", "network"
]

LOCAL_COMMUNITY_KEYWORDS: List[str] = [
    "community center", "community centre", "family services",
    "food bank", "food pantry", "soup kitchen", "shelter",
    "clinic", "school", "youth group", "local community",
    "serving the community of"
]

INACTIVE_PHRASES: List[str] = [
    "has now closed",
    "has closed",
    "ceased operations",
    "ceased to operate",
    "no longer operating",
    "no longer exists",
    "has been wound up",
    "has now been wound up",
    "this organisation has closed",
    "this organization has closed",
    "was dissolved",
    "has been dissolved",
    "has now been dissolved",
    "dissolved on",
]

ARCHIVE_PHRASES: List[str] = [
    "this website is an archive",
    "this site is an archive",
    "this site is no longer updated",
    "this website is no longer updated",
    "for historical reference only",
    "archived version of the site",
]


# ---------- Helpers ----------

def fetch_url(url: str) -> str:
    """
    Fetch HTML and return lower-cased visible text.
    Also tries /about, /mission, /history, /governance.
    """
    if not url:
        return ""

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0 Safari/537.36"
        )
    }

    def _safe_get(u: str) -> str:
        try:
            resp = requests.get(u, headers=headers, timeout=8)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "noscript"]):
                tag.decompose()
            return soup.get_text(separator=" ", strip=True).lower()
        except Exception:
            return ""

    url = url.strip()
    if url.endswith("/"):
        base = url[:-1]
    else:
        base = url

    full_text = _safe_get(url)

    for suffix in ("/about", "/mission", "/history", "/governance"):
        extra = _safe_get(base + suffix)
        if extra:
            full_text += " " + extra

    return full_text


def count_matches(text: str, keywords: List[str]) -> int:
    total = 0
    for kw in keywords:
        if kw in text:
            total += text.count(kw)
    return total


def normalize_scores(scores: Dict[str, float]) -> Dict[str, float]:
    total = float(sum(v for v in scores.values() if v > 0))
    if total <= 0:
        return {k: 0.0 for k in scores}
    return {k: (v / total) * 100.0 for k, v in scores.items()}


# ---------- Religion detection ----------
def detect_religion(text: str, name: str) -> Tuple[str, Dict[str, float], float]:
    """
    Определяем религию с аккуратной обработкой Multi-faith:
    - сначала смотрим на основные религии (Islam / Christianity / Judaism)
    - Multi-faith побеждает только если НЕТ сильного сигнала одной религии
      или если в названии явно сказано, что это interfaith / multi-faith network.
    """
    combined = f"{name.lower()} {text or ''}"

    # базовые счёты по всем ключам
    scores: Dict[str, float] = {}
    for rel, kws in RELIGION_KEYWORDS.items():
        scores[rel] = float(count_matches(combined, kws))

    generic_score = float(count_matches(combined, GENERIC_FAITH_KEYWORDS))

    # разложим на основные религии и multi-faith
    main_rels = ["Islam", "Christianity", "Judaism"]
    main_scores = {r: scores.get(r, 0.0) for r in main_rels}
    multi_score = scores.get("Multi-faith", 0.0)

    max_main_rel, max_main_val = max(main_scores.items(), key=lambda x: x[1])

    # если вообще нет религиозных сигналов
    if max_main_val == 0 and multi_score == 0 and generic_score == 0:
        return "Other/Unknown", scores, 0.0

    # 1) Явный interfaith network в названии → Multi-faith
    if ("interfaith" in name.lower() or "multi-faith" in name.lower()
            or "multi faith" in name.lower()):
        if multi_score == 0:
            multi_score = 1.0
            scores["Multi-faith"] = multi_score
        norm = normalize_scores(scores)
        return "Multi-faith", scores, norm.get("Multi-faith", 80.0)

    # 2) Есть приличный сигнал одной религии → она важнее Multi-faith
    #    (даже если сайт упоминает interfaith инициативы)
    if max_main_val >= 2 or max_main_val > multi_score:
        norm = normalize_scores(scores)
        return max_main_rel, scores, norm.get(max_main_rel, 0.0)

    # 3) Сильный multi-faith сигнал и почти нет одной конкретной религии
    if multi_score > 0 and max_main_val == 0:
        norm = normalize_scores(scores)
        return "Multi-faith", scores, norm.get("Multi-faith", 0.0)

    # 4) fallback: если всё примерно на нуле, но есть generic faith
    if max_main_val == 0 and generic_score > 0:
        # считаем это "Other/Unknown", но религиозным
        scores["GenericFaith"] = generic_score
        norm = normalize_scores(scores)
        return "Other/Unknown", scores, norm.get("Other/Unknown", 0.0)

    # 5) по умолчанию — та основная религия, которая набрала больше всего
    norm = normalize_scores(scores)
    return max_main_rel, scores, norm.get(max_main_rel, 0.0)

# ---------- Type (FBCore / FBOrigin / FBCommunity / Not-FB) ----------

def detect_type(text: str, name: str, religion: str) -> Tuple[str, Dict[str, float], float]:
    combined = f"{name.lower()} {text or ''}"

    scores = {
        "FBCore": 0.0,
        "FBOrigin": 0.0,
        "FBCommunity": 0.0,
        "Not-FB": 0.0,
    }

    # FBCore — явные места поклонения / приходы и т.п.
    core_hits = (
        count_matches(combined, WORSHIP_PLACE_KEYWORDS)
        + count_matches(combined, WORSHIP_PRACTICE_KEYWORDS)
    )
    if any(w in combined for w in ["parish", "diocese", "cathedral", "chapel"]):
        core_hits += 2
    scores["FBCore"] += float(core_hits)

    # FBOrigin — религиозное происхождение / управление
    origin_keywords = [
        "founded by the catholic church",
        "founded by the church",
        "founded by the methodist church",
        "founded by the presbyterian church",
        "founded by the episcopal church",
        "founded by the lutheran church",
        "founded by the anglican church",
        "jesuit university",
        "jesuit college",
        "sponsored by the church",
        "sponsored by the diocese",
        "owned by the church",
        "catholic health system",
        "christian health system",
        "faith-based hospital"
    ]
    scores["FBOrigin"] += float(count_matches(combined, origin_keywords))

    # FBCommunity — светская миссия, но религиозная аудитория
    community_keywords = [
        "friends of", "supporting the work of", "in partnership with synagogues",
        "in partnership with churches", "supported by congregations",
        "supported by parishes", "supported by local churches",
        "supported by mosques", "supported by the jewish community",
        "supported by the muslim community", "supported by the christian community"
    ]
    comm_hits = (
        count_matches(combined, LOCAL_COMMUNITY_KEYWORDS)
        + count_matches(combined, community_keywords)
    )
    # если религия определена (не Other/Unknown) и есть сильные community/relief сигналы
    if religion in {"Christianity", "Islam", "Judaism", "Multi-faith"}:
        comm_hits += count_matches(combined, GLOBAL_NGO_KEYWORDS) * 0.3
    scores["FBCommunity"] += float(comm_hits)

    # базовый Not-FB, если религиозных сигналов мало
    if all(v == 0 for k, v in scores.items() if k != "Not-FB"):
        scores["Not-FB"] = 1.0

    # выбор типа
    best_type = max(scores.items(), key=lambda x: x[1])[0]
    norm = normalize_scores(scores)
    type_conf = norm.get(best_type, 0.0)

    return best_type, scores, type_conf


# ---------- Activity status ----------

def detect_activity(text: str, name: str) -> Tuple[str, Dict[str, float], float]:
    combined = f"{name.lower()} {text or ''}"

    inactive_hits = count_matches(combined, [p.lower() for p in INACTIVE_PHRASES])
    archive_hits = count_matches(combined, [p.lower() for p in ARCHIVE_PHRASES])

    scores = {
        "Inactive": float(inactive_hits + archive_hits),
        "Likely active": 0.0,
        "Unknown": 0.0,
    }

    if scores["Inactive"] > 0:
        status = "Inactive"
    else:
        # грубая эвристика: если сайт вообще живой и без archive-фраз → likely active
        if combined.strip():
            scores["Likely active"] = 1.0
            status = "Likely active"
        else:
            scores["Unknown"] = 1.0
            status = "Unknown"

    norm = normalize_scores(scores)
    act_conf = norm.get(status, 0.0)

    return status, scores, act_conf


# ---------- Public entrypoint ----------

def classify_organization(name: str, url: str) -> Dict[str, Any]:
    """
    Main entrypoint used by Streamlit UI.
    Returns labels + per-dimension confidence + raw scores.
    """
    text = fetch_url(url)

    religion, rel_scores, rel_conf = detect_religion(text, name)
    fb_type, type_scores, type_conf = detect_type(text, name, religion)
    activity, act_scores, act_conf = detect_activity(text, name)

    return {
        "type": fb_type,
        "religion": religion,
        "activity_status": activity,
        "confidence": {
            "type": type_conf,
            "religion": rel_conf,
            "activity": act_conf,
        },
        "scores": {
            "type": type_scores,
            "religion": rel_scores,
            "activity": act_scores,
        },
        "debug": {
            "fetched_text_length": len(text or ""),
        },
    }
