import logging
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://parking.fullerton.edu/parkinglotcounts/mobile.aspx"
USER_AGENT = "Mozilla/5.0 (compatible; SmartParkBot/1.0; +https://example.com)"
REQUEST_TIMEOUT = 30

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    value: Any
    ts: float


_summary_cache: Optional[CacheEntry] = None
_levels_cache: Dict[str, CacheEntry] = {}
CACHE_SECONDS = 60


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Referer": BASE_URL,
        }
    )
    return s


def _clean_text(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


def _parse_int(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    value = _clean_text(value).replace(",", "")
    if value.isdigit():
        return int(value)
    return None


def _normalize_status(status_text: str) -> Tuple[Optional[int], str]:
    status_text = _clean_text(status_text)
    numeric = _parse_int(status_text)
    if numeric is not None:
        return numeric, status_text

    lowered = status_text.lower()
    if lowered == "full":
        return 0, status_text
    if lowered == "open":
        return None, status_text
    if lowered == "closed":
        return None, status_text

    return None, status_text


def _get_hidden_fields(soup: BeautifulSoup) -> Dict[str, str]:
    fields: Dict[str, str] = {}
    for inp in soup.select("input[type='hidden'][name]"):
        fields[inp.get("name")] = inp.get("value", "")
    return fields


def _get_cache(entry: Optional[CacheEntry]) -> Optional[Any]:
    if entry and time.time() - entry.ts < CACHE_SECONDS:
        return entry.value
    return None


def _set_summary_cache(value: Any) -> None:
    global _summary_cache
    _summary_cache = CacheEntry(value=value, ts=time.time())


def _set_levels_cache(key: str, value: Any) -> None:
    _levels_cache[key] = CacheEntry(value=value, ts=time.time())


def _get_levels_cache(key: str) -> Optional[Any]:
    entry = _levels_cache.get(key)
    if entry and time.time() - entry.ts < CACHE_SECONDS:
        return entry.value
    return None


def fetch_main_page(session: Optional[requests.Session] = None) -> Tuple[requests.Session, requests.Response]:
    session = session or _session()
    resp = session.get(BASE_URL, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return session, resp


def parse_lot_summary(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("tr")

    lots: List[Dict[str, Any]] = []

    for row in rows:
        name_el = row.select_one(
            'a[id^="GridView_All_LinkButton_LocName_"], span[id^="GridView_All_Label_LocName_"]'
        )
        total_el = row.select_one('span[id^="GridView_All_Label_Avail_"]')
        status_el = row.select_one('span[id^="GridView_All_Label_AllSpots_"]')
        updated_el = row.select_one('span[id^="GridView_All_Label_LastUpdated_"]')
        lot_id_el = row.select_one('input[id^="GridView_All_HiddenField_LotID_"]')
        levels_link_el = row.select_one('a[id^="GridView_All_LinkButton_Levels_"]')

        if not name_el or not total_el or not status_el:
            continue

        name = _clean_text(name_el.get_text())
        total_spots = _parse_int(total_el.get_text())
        status_text = _clean_text(status_el.get_text())
        available, status_text = _normalize_status(status_text)
        last_updated = _clean_text(updated_el.get_text()) if updated_el else ""
        lot_id = lot_id_el.get("value", "").strip() if lot_id_el else ""

        lots.append(
            {
                "lot_id": lot_id,
                "name": name,
                "total_spots": total_spots,
                "available": available,
                "status_text": status_text,
                "last_updated": last_updated,
                "source": BASE_URL,
                "has_levels": bool(levels_link_el),
                "levels": [],
            }
        )

    return lots


def build_summary(lots: List[Dict[str, Any]]) -> Dict[str, Any]:
    total_spots_sum = sum(x["total_spots"] or 0 for x in lots)
    total_available_sum = sum(x["available"] for x in lots if isinstance(x.get("available"), int))
    last_updated_values = [x["last_updated"] for x in lots if x.get("last_updated")]

    return {
        "total_spots_sum": total_spots_sum,
        "total_available_sum": total_available_sum,
        "lot_count": len(lots),
        "last_updated_max": max(last_updated_values) if last_updated_values else "",
    }


def fetch_lot_summary(force_refresh: bool = False) -> Dict[str, Any]:
    if not force_refresh:
        cached = _get_cache(_summary_cache)
        if cached is not None:
            return cached

    session, resp = fetch_main_page()
    lots = parse_lot_summary(resp.text)
    payload = {
        "summary": build_summary(lots),
        "lots": lots,
        "stale": False,
    }
    _set_summary_cache(payload)
    return payload


def _find_lot_row_and_event_target(
    html: str,
    lot_name: Optional[str] = None,
    lot_id: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    soup = BeautifulSoup(html, "html.parser")

    for row in soup.select("tr"):
        name_el = row.select_one(
            'a[id^="GridView_All_LinkButton_LocName_"], span[id^="GridView_All_Label_LocName_"]'
        )
        hidden_lot_id_el = row.select_one('input[id^="GridView_All_HiddenField_LotID_"]')
        levels_link_el = row.select_one('a[id^="GridView_All_LinkButton_Levels_"]')

        if not name_el or not levels_link_el:
            continue

        name = _clean_text(name_el.get_text())
        row_lot_id = hidden_lot_id_el.get("value", "").strip() if hidden_lot_id_el else ""
        matches = False

        if lot_name and name.lower() == lot_name.lower():
            matches = True
        if lot_id and row_lot_id == str(lot_id):
            matches = True

        if matches:
            href = levels_link_el.get("href", "")
            match = re.search(r"__doPostBack\('([^']+)'", href)
            if match:
                return row_lot_id, match.group(1)

    return None, None


def _postback_for_levels(
    session: requests.Session,
    html: str,
    event_target: str,
) -> str:
    soup = BeautifulSoup(html, "html.parser")
    fields = _get_hidden_fields(soup)

    form = fields.copy()
    form["__EVENTTARGET"] = event_target
    form["__EVENTARGUMENT"] = ""
    form.setdefault("__LASTFOCUS", "")

    resp = session.post(BASE_URL, data=form, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return resp.text


def parse_levels_html(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    levels: List[Dict[str, Any]] = []

    for row in soup.select("tr"):
        name_el = row.select_one('span[id^="GridView_Levels_Label_LevName_"]')
        total_el = row.select_one('span[id^="GridView_Levels_Label_TotalSpotsLevel_"]')
        updated_el = row.select_one('span[id^="GridView_Levels_Label_LastUpdated_"]')
        status_el = row.select_one('span[id^="GridView_Levels_Label_AvailForLevel_"]')

        if not name_el or not total_el or not status_el:
            continue

        level_name = _clean_text(name_el.get_text())
        total_spots = _parse_int(total_el.get_text())
        status_text = _clean_text(status_el.get_text())
        available, status_text = _normalize_status(status_text)
        last_updated = _clean_text(updated_el.get_text()) if updated_el else ""

        if not level_name:
            logger.warning("Skipping level row with empty level name")
            continue

        levels.append(
            {
                "level_name": level_name,
                "total_spots": total_spots,
                "available": available,
                "status_text": status_text,
                "last_updated": last_updated,
            }
        )

    return levels


def fetch_lot_levels(
    lot_name: Optional[str] = None,
    lot_id: Optional[str] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    cache_key = (lot_name or lot_id or "").lower()
    if not force_refresh and cache_key:
        cached = _get_levels_cache(cache_key)
        if cached is not None:
            return cached

    session, resp = fetch_main_page()
    row_lot_id, event_target = _find_lot_row_and_event_target(resp.text, lot_name=lot_name, lot_id=lot_id)

    if not event_target:
        payload = {
            "lot_name": lot_name or "",
            "lot_id": row_lot_id or lot_id or "",
            "has_levels": False,
            "levels": [],
            "stale": False,
        }
        if cache_key:
            _set_levels_cache(cache_key, payload)
        return payload

    levels_html = _postback_for_levels(session, resp.text, event_target)
    levels = parse_levels_html(levels_html)

    payload = {
        "lot_name": lot_name or "",
        "lot_id": row_lot_id or lot_id or "",
        "has_levels": bool(levels),
        "levels": levels,
        "stale": False,
    }

    if cache_key:
        _set_levels_cache(cache_key, payload)
    return payload


def fetch_all_lots_with_levels(force_refresh: bool = False) -> Dict[str, Any]:
    summary_payload = fetch_lot_summary(force_refresh=force_refresh)
    lots = summary_payload["lots"]

    for lot in lots:
        if not lot.get("has_levels"):
            lot["levels"] = []
            continue

        try:
            level_payload = fetch_lot_levels(
                lot_name=lot["name"],
                lot_id=lot["lot_id"],
                force_refresh=force_refresh,
            )
            lot["has_levels"] = level_payload["has_levels"]
            lot["levels"] = level_payload["levels"]
        except Exception as exc:
            logger.warning("Failed to fetch levels for %s: %s", lot["name"], exc)
            lot["levels"] = []

    payload = {
        "summary": build_summary(lots),
        "lots": lots,
        "stale": False,
    }
    _set_summary_cache(payload)
    return payload