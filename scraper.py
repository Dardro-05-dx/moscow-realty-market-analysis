"""Сбор открытых объявлений о продаже квартир в Москве с mirkvartir.ru.

Обходит только публичные HTML-страницы и уважает robots.txt.
Не пытается обходить ограничения, капчи и блокировки.
"""
from __future__ import annotations

from datetime import datetime, timezone
import re
import time
from typing import Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup, Tag

BASE_URL = "https://www.mirkvartir.ru/Москва/"
USER_AGENT = "MoscowRealtyEducationalScraper/1.0 (personal research; low-volume)"
PRICE_RE = re.compile(r"(\d[\d \u00a0\u202f]*)\s*(?:₽|руб\.?)", re.I)
AREA_RE = re.compile(r"(?<![\d/])(\d{1,3}(?:[.,]\d{1,2})?)\s*м[²2]\s*(?:площадь)?", re.I)
ROOMS_RE = re.compile(r"\b([1-9])\s*(?:[- ]комн(?:ат)?|комнат[аы]?)\b", re.I)
METROS = {
    "Шаболовская", "Толстопальцево", "Шелепиха", "Кунцевская", "Бабушкинская",
    "Потапово", "Планерная", "Парк культуры", "Маяковская", "Арбатская",
    "Белорусская", "Киевская", "Тверская", "Сокол", "Аэропорт", "Раменки",
    "Автозаводская", "Медведково", "Динамо", "Таганская", "Китай-город",
    "Бауманская", "Тульская", "Профсоюзная", "Университет", "ВДНХ",
    "Ботанический сад", "Пушкинская", "Октябрьская", "Фили", "Беляево",
    "Митино", "Фрунзенская", "Полежаевская", "Новые Черёмушки", "Охотный Ряд",
}


def as_number(raw: str) -> float:
    return float(re.sub(r"[^\d.,]", "", raw).replace(",", "."))


def _choose_card(anchor: Tag) -> Optional[Tag]:
    """Выбирает минимальный контейнер с ценой, площадью и комнатностью."""
    fallback = None
    for ancestor in list(anchor.parents)[:10]:
        if not isinstance(ancestor, Tag) or ancestor.name in ("html", "body"):
            break
        text = ancestor.get_text(" ", strip=True)
        if not (AREA_RE.search(text) and (ROOMS_RE.search(text) or "Студия" in text)):
            continue
        if len(text) > 5000:
            break
        price_anchors = sum(
            1 for a in ancestor.find_all("a", href=True)
            if "₽" in a.get_text(" ", strip=True)
            and "/м²" in a.get_text(" ", strip=True)
        )
        if price_anchors > 1:
            break
        fallback = ancestor
        if "Москва" in text:
            return ancestor
    return fallback


def _extract_address(card: Tag) -> str:
    pieces = [x.strip() for x in card.stripped_strings if x.strip()]
    for index, piece in enumerate(pieces):
        if piece in ("Москва", "Москва,"):
            rest = []
            for part in pieces[index + 1:index + 5]:
                if any(stop in part for stop in ("На карте", "Позвонить", "Поделиться", "Добавить в избранное")):
                    break
                if len(part) > 85:
                    break
                rest.append(part.strip(" ,"))
            addr = ", ".join(x for x in rest if x)
            return "Москва" + (", " + addr if addr else "")
        if "Москва," in piece and len(piece) < 140:
            return piece[:140].strip()
    return "Москва (адрес не извлечён)"


def parse_listings(html: str, page_url: str = BASE_URL) -> list[dict]:
    """Парсит карточки каталога с ценовыми ссылками; не собирает контакты продавцов."""
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []
    seen: set[str] = set()
    for a in soup.find_all("a", href=True):
        price_text = a.get_text(" ", strip=True)
        if not ("₽" in price_text and re.search(r"₽\s*/\s*м[²2]", price_text)):
            continue
        price_match = PRICE_RE.search(price_text)
        if not price_match:
            continue
        price = int(as_number(price_match.group(1)))
        if not 500_000 <= price <= 3_000_000_000:
            continue
        url = urljoin(page_url, a["href"])
        # Не переходить на внешние домены и не принимать ссылки на поиск.
        if urlparse(url).hostname not in ("mirkvartir.ru", "www.mirkvartir.ru"):
            continue
        if url in seen or not re.search(r"/\d{5,}/?", urlparse(url).path):
            continue
        card = _choose_card(a)
        if card is None:
            continue
        card_text = card.get_text(" ", strip=True)
        area_match = AREA_RE.search(card_text)
        if area_match is None:
            continue
        area = as_number(area_match.group(1))
        if not 8 <= area <= 500:
            continue
        room_match = ROOMS_RE.search(card_text)
        rooms = int(room_match.group(1)) if room_match else (0 if re.search(r"\bстудия\b", card_text, re.I) else None)
        if rooms is None:
            continue
        # Площадь из карточки, цена за квадратный метр пересчитывается из цены.
        district_match = re.search(r"\bрайон(?:е|а)?\s+([А-ЯЁ][А-ЯЁа-яё\-]{2,})", card_text)
        metro = ""
        for link in card.find_all("a", href=True):
            candidate = link.get_text(" ", strip=True)
            if candidate in METROS:
                metro = candidate
                break
        price_per_m2 = round(price / area)
        seen.add(url)
        results.append({
            "url": url,
            "title": ("Студия" if rooms == 0 else f"{rooms}-комнатная квартира"),
            "price_rub": price,
            "area_m2": area,
            "rooms": rooms,
            "price_per_m2_rub": price_per_m2,
            "address": _extract_address(card),
            "district": district_match.group(1) if district_match else "",
            "metro": metro,
            "source": "mirkvartir.ru",
            "collected_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
    return results


def find_next_page(html: str, current_url: str) -> Optional[str]:
    soup = BeautifulSoup(html, "html.parser")
    for a in soup.select('a[rel~="next"], a[href]'):
        label = a.get_text(" ", strip=True).lower()
        rel = a.get("rel") or []
        if "next" in rel or re.search(r"(?:следующая|дальше|далее|впер[её]д|^›$|^→$)", label):
            next_url = urljoin(current_url, a["href"])
            if urlparse(next_url).hostname == urlparse(BASE_URL).hostname and next_url != current_url:
                return next_url
    return None


def check_robots(session: requests.Session, url: str) -> RobotFileParser:
    parts = urlparse(url)
    robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
    try:
        response = session.get(robots_url, timeout=20)
        if response.status_code == 404:
            # Согласно robots conventions, отсутствующий robots.txt не задаёт запрета.
            parser = RobotFileParser()
            parser.parse([])
            return parser
        response.raise_for_status()
    except requests.RequestException as exc:
        raise RuntimeError(f"Не удалось проверить robots.txt ({robots_url}): {exc}. Сбор остановлен.") from exc
    parser = RobotFileParser()
    parser.parse(response.text.splitlines())
    return parser


def scrape_live(max_pages: int = 1, delay_seconds: float = 4) -> list[dict]:
    if not 1 <= max_pages <= 10:
        raise ValueError("Разрешено от 1 до 10 страниц за один запуск")
    if delay_seconds < 3:
        raise ValueError("Интервал между запросами должен быть не менее 3 секунд")
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "ru"})
    robots = check_robots(session, BASE_URL)
    all_rows: list[dict] = []
    visited: set[str] = set()
    url = BASE_URL
    for page in range(1, max_pages + 1):
        if url in visited:
            break
        if not robots.can_fetch(USER_AGENT, url):
            raise RuntimeError(f"robots.txt запрещает автоматический доступ к {url}. Сбор остановлен.")
        if page > 1:
            time.sleep(delay_seconds)
        try:
            response = session.get(url, timeout=25)
            response.raise_for_status()
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            raise RuntimeError(
                f"Источник ответил HTTP {status}. Без обхода защиты: используйте разрешённый экспорт/API "
                "или офлайн-режим --mode sample."
            ) from exc
        except requests.RequestException as exc:
            raise RuntimeError(f"Ошибка соединения с источником: {exc}") from exc
        visited.add(url)
        rows = parse_listings(response.text, url)
        print(f"Страница {page}: {len(rows)} объявлений — {url}")
        all_rows.extend(rows)
        url = find_next_page(response.text, url)
        if not url:
            break
    unique = {row["url"]: row for row in all_rows}
    if not unique:
        raise RuntimeError(
            "На сайте не удалось распознать объявления. Вероятно, изменилась структура HTML, "
            "страница требует JavaScript или ограничен автоматический доступ. "
            "Проверьте парсер и условия использования сайта."
        )
    return list(unique.values())
