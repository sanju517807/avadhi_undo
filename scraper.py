"""Avadhi Undo MVP scraper.

Reads official Kerala I&PRD press releases, identifies recent district-level
holiday notices, updates status.json, and optionally sends a Telegram alert.

This is intentionally conservative: an article must look like an actual
holiday/closure notice and its target date must be today before it is marked
ACTIVE. Unknown cases remain UNKNOWN rather than being guessed as a holiday.
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_DIR = Path(__file__).resolve().parent
STATUS_PATH = BASE_DIR / "status.json"
CONFIG_PATH = BASE_DIR / "config.json"
TIMEOUT = 20
PRD_URL = "https://prd.kerala.gov.in/ml/pressrelease"
TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"

DISTRICT_ALIASES = {
    "ernakulam": ["Ernakulam", "എറണാകുളം"],
    "trivandrum": ["Thiruvananthapuram", "Trivandrum", "തിരുവനന്തപുരം"],
    "thrissur": ["Thrissur", "തൃശ്ശൂർ", "തൃശൂർ"],
    "kozhikode": ["Kozhikode", "കോഴിക്കോട്"],
}

HOLIDAY_TERMS = [
    "അവധി", "holiday", "closed", "closure", "വിദ്യാഭ്യാസ സ്ഥാപനങ്ങൾക്ക്",
    "വിദ്യാഭ്യാസ സ്ഥാപനങ്ങള്‍ക്ക്", "ഓഫീസുകൾക്കും അവധി", "ഓഫീസുകള്‍ക്കും അവധി",
]

INSTITUTION_TERMS = {
    "schools": ["school", "schools", "സ്കൂള", "വിദ്യാലയ"],
    "colleges": ["college", "colleges", "കോളേജ്", "പ്രൊഫഷണൽ കോളേജ്", "പ്രൊഫഷണല്‍ കോളേജ്"],
    "government_offices": ["government office", "government offices", "സർക്കാർ ഓഫീസ", "സര്‍ക്കാര്‍ ഓഫീസ"],
}

TODAY_WORDS = ["today", "ഇന്ന്"]
TOMORROW_WORDS = ["tomorrow", "നാളെ"]


def now_ist() -> datetime:
    return datetime.now(timezone(timedelta(hours=5, minutes=30)))


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path: Path, data: dict[str, Any]) -> None:
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    temp.replace(path)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


def detect_district(text: str) -> str | None:
    lowered = normalize(text)
    for district, aliases in DISTRICT_ALIASES.items():
        if any(normalize(alias) in lowered for alias in aliases):
            return district
    return None


def detect_institutions(text: str) -> set[str]:
    lowered = normalize(text)
    found: set[str] = set()
    for institution, terms in INSTITUTION_TERMS.items():
        if any(normalize(term) in lowered for term in terms):
            found.add(institution)
    if "വിദ്യാഭ്യാസ സ്ഥാപന" in lowered or "educational institutions" in lowered:
        found.update({"schools", "colleges"})
    return found


def parse_target_date(text: str, today: date) -> date | None:
    # Handles common numeric forms such as 01/07/26, 01/07/2026 and
    # 01-07-26. These occur frequently in official holiday notices.
    for match in re.findall(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b", text):
        day, month, year = map(int, match)
        if year < 100:
            year += 2000
        try:
            return date(year, month, day)
        except ValueError:
            continue

    lowered = normalize(text)
    if any(word in lowered for word in TODAY_WORDS):
        return today
    if any(word in lowered for word in TOMORROW_WORDS):
        return today + timedelta(days=1)
    return None


def looks_like_holiday(text: str) -> bool:
    lowered = normalize(text)
    return any(term in lowered for term in HOLIDAY_TERMS)


def fetch(url: str) -> str:
    response = requests.get(
        url,
        timeout=TIMEOUT,
        headers={"User-Agent": "AvadhiUndo/1.0 (+https://github.com/sanju517807/avadhi_undo)"},
    )
    response.raise_for_status()
    response.encoding = response.apparent_encoding or response.encoding
    return response.text


def collect_recent_prd_articles() -> list[dict[str, str]]:
    html = fetch(PRD_URL)
    soup = BeautifulSoup(html, "html.parser")
    articles: list[dict[str, str]] = []
    seen: set[str] = set()

    for link in soup.find_all("a", href=True):
        title = link.get_text(" ", strip=True)
        href = urljoin(PRD_URL, link["href"])
        if not title or href in seen:
            continue
        if "/node/" not in href:
            continue
        seen.add(href)
        articles.append({"title": title, "url": href})
        if len(articles) >= 60:
            break

    return articles


def inspect_article(article: dict[str, str], today: date) -> dict[str, Any] | None:
    try:
        html = fetch(article["url"])
    except requests.RequestException as exc:
        print(f"Skipping {article['url']}: {exc}")
        return None

    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    combined = f"{article['title']} {text}"

    if not looks_like_holiday(combined):
        return None

    district = detect_district(combined)
    if not district:
        return None

    target_date = parse_target_date(combined, today)
    if target_date != today:
        return None

    institutions = detect_institutions(combined)
    if not institutions:
        institutions = {"other_institutions"}

    return {
        "district": district,
        "institutions": sorted(institutions),
        "title": article["title"],
        "source_url": article["url"],
        "published_at": "",
        "target_date": today.isoformat(),
    }


def empty_institution() -> dict[str, str]:
    return {"status": "unknown", "title": "No verified closure order found."}


def update_status(data: dict[str, Any], findings: list[dict[str, Any]], timestamp: str) -> None:
    for district in data.get("districts", {}).values():
        district["holiday"] = {
            "status": "unknown",
            "title": "No verified holiday order found yet.",
            "source_url": "",
            "published_at": "",
            "target_date": "",
        }
        for key in ("schools", "colleges", "government_offices", "other_institutions"):
            district.setdefault("institutions", {})[key] = empty_institution()

    for finding in findings:
        district = data["districts"][finding["district"]]
        district["holiday"] = {
            "status": "active",
            "title": finding["title"],
            "source_url": finding["source_url"],
            "published_at": finding["published_at"],
            "target_date": finding["target_date"],
        }
        for institution in finding["institutions"]:
            district["institutions"][institution] = {
                "status": "active",
                "title": finding["title"],
            }

    data["last_updated"] = timestamp


def send_telegram_alert(finding: dict[str, Any], token: str, channel: str) -> None:
    message = (
        f"🔴 AVADHI UNDO — {finding['district'].title()}\n\n"
        f"{finding['title']}\n\n"
        f"📅 Effective: {finding['target_date']}\n"
        f"🔗 Official source: {finding['source_url']}"
    )
    response = requests.post(
        TELEGRAM_API.format(token=token),
        data={"chat_id": channel, "text": message, "disable_web_page_preview": False},
        timeout=TIMEOUT,
    )
    response.raise_for_status()


def main() -> None:
    config = load_json(CONFIG_PATH)
    status = load_json(STATUS_PATH)
    current = now_ist()
    today = current.date()
    timestamp = current.isoformat()

    print(f"Avadhi Undo check: {current.isoformat()}")
    print(f"Source: {PRD_URL}")

    try:
        candidates = collect_recent_prd_articles()
        findings = []
        for article in candidates:
            finding = inspect_article(article, today)
            if finding:
                findings.append(finding)

        # De-duplicate by district + source URL.
        unique = {(item["district"], item["source_url"]): item for item in findings}
        findings = list(unique.values())
        print(f"Holiday findings for {today}: {len(findings)}")

        previous = status.get("districts", {})
        update_status(status, findings, timestamp)
        save_json(STATUS_PATH, status)

        token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        channel = config.get("telegram", {}).get("channel", "@avadhiundo")

        for finding in findings:
            old = previous.get(finding["district"], {}).get("holiday", {})
            was_active = old.get("status") == "active" and old.get("source_url") == finding["source_url"]
            if token and config.get("telegram", {}).get("enabled", True) and not was_active:
                try:
                    send_telegram_alert(finding, token, channel)
                    print(f"Telegram alert sent for {finding['district']}")
                except requests.RequestException as exc:
                    print(f"Telegram alert failed: {exc}")

    except requests.RequestException as exc:
        # Keep the last known state if the official source is temporarily down.
        status["last_updated"] = timestamp
        status["source_error"] = str(exc)
        save_json(STATUS_PATH, status)
        print(f"Source unavailable; retained last known data: {exc}")


if __name__ == "__main__":
    main()
