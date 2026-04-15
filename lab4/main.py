from __future__ import annotations

import argparse
import json
import logging
import re
import shutil
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import local
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup, NavigableString, Tag
from requests import Session
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = ROOT / "outputs"
OUTPUT_DATA_DIR = OUTPUT_ROOT / "data"
OUTPUT_LOGS_DIR = OUTPUT_ROOT / "logs"
OUTPUT_REPORTS_DIR = OUTPUT_ROOT / "reports"
CACHE_DIR = OUTPUT_DATA_DIR / "cache"
README_FILE = ROOT / "README.md"
REPORT_FILE = ROOT / "report.md"
HADOOP_REPORT_FILE = ROOT / "hadoop_report.md"
COMBINED_REPORT_CONTEXT_FILE = OUTPUT_DATA_DIR / "report_context.json"
LOCAL_HADOOP_HOME = ROOT / "tools" / "hadoop-3.4.2"

BASE_URL = "https://www1.fips.ru"
REGISTERS_ROOT_URL = f"{BASE_URL}/registers-web/"
REGISTER_ACTION_URL = f"{BASE_URL}/registers-web/action?acName=clickRegister&regName={{reg_name}}"

DEFAULT_REQUEST_TIMEOUT = 60
DEFAULT_TREE_DELAY = 0.35
DEFAULT_DOC_DELAY = 0.35
DEFAULT_FLUSH_EVERY = 10
DEFAULT_WORKERS = 12

INTERVAL_RE = re.compile(r"^\s*(\d[\d ]*)\s*-\s*(\d[\d ]*)\s*$")
DATE_RE = re.compile(r"\b(\d{2}\.\d{2}\.\d{4})\b")
STATUS_RE = re.compile(r"^(?P<status>.+?)\s*\(последнее изменение статуса:\s*(?P<date>\d{2}\.\d{2}\.\d{4})\)$")
WHITESPACE_RE = re.compile(r"\s+")
DAILY_DOC_LIMIT_TEXT = "Превышен допустимый предел количества просмотров документов в день"


class DailyViewLimitExceededError(RuntimeError):
    """FIPS blocks further document views for the current IP until the next day."""


@dataclass(frozen=True)
class Interval:
    start: int
    end: int

    @property
    def label(self) -> str:
        return f"{self.start} - {self.end}"

    def overlaps(self, other: "Interval") -> bool:
        return self.start <= other.end and other.start <= self.end

    def contains(self, other: "Interval") -> bool:
        return self.start <= other.start and other.end <= self.end


@dataclass(frozen=True)
class RegistryConfig:
    slug: str
    title: str
    reg_name: str
    db_name: str
    patent_type: str
    patent_type_ru: str

    @property
    def register_url(self) -> str:
        return REGISTER_ACTION_URL.format(reg_name=self.reg_name)


REGISTRIES: dict[str, RegistryConfig] = {
    "inventions": RegistryConfig(
        slug="inventions",
        title="Реестр изобретений",
        reg_name="RUPAT",
        db_name="RUPAT",
        patent_type="invention",
        patent_type_ru="изобретение",
    ),
    "utility_models": RegistryConfig(
        slug="utility_models",
        title="Реестр полезных моделей",
        reg_name="RUPM",
        db_name="RUPM",
        patent_type="utility_model",
        patent_type_ru="полезная модель",
    ),
}


# Для варианта 16 диапазон полезных моделей восстановлен по последовательности из таблицы.
VARIANT_RANGES: dict[int, dict[str, Interval]] = {
    1: {"inventions": Interval(2_800_000, 2_899_999), "utility_models": Interval(241_000, 241_999)},
    2: {"inventions": Interval(2_700_000, 2_799_999), "utility_models": Interval(240_000, 240_999)},
    3: {"inventions": Interval(2_600_000, 2_699_999), "utility_models": Interval(230_000, 239_999)},
    4: {"inventions": Interval(2_500_000, 2_599_999), "utility_models": Interval(229_000, 229_999)},
    5: {"inventions": Interval(2_400_000, 2_499_999), "utility_models": Interval(228_000, 228_999)},
    6: {"inventions": Interval(2_300_000, 2_399_999), "utility_models": Interval(227_000, 227_999)},
    7: {"inventions": Interval(2_200_000, 2_299_999), "utility_models": Interval(226_000, 226_999)},
    8: {"inventions": Interval(2_100_000, 2_199_999), "utility_models": Interval(225_000, 225_999)},
    9: {"inventions": Interval(2_000_000, 2_099_999), "utility_models": Interval(224_000, 224_999)},
    10: {"inventions": Interval(1_800_000, 1_899_999), "utility_models": Interval(223_000, 223_999)},
    11: {"inventions": Interval(1_700_000, 1_799_999), "utility_models": Interval(222_000, 222_999)},
    12: {"inventions": Interval(1_600_000, 1_699_999), "utility_models": Interval(221_000, 221_999)},
    13: {"inventions": Interval(1_500_000, 1_599_999), "utility_models": Interval(220_000, 220_999)},
    14: {"inventions": Interval(1_400_000, 1_499_999), "utility_models": Interval(219_000, 219_999)},
    15: {"inventions": Interval(1_300_000, 1_399_999), "utility_models": Interval(218_000, 218_999)},
    16: {"inventions": Interval(1_200_000, 1_299_999), "utility_models": Interval(217_000, 217_999)},
}


def ensure_output_dirs() -> None:
    for directory in [OUTPUT_ROOT, OUTPUT_DATA_DIR, OUTPUT_LOGS_DIR, OUTPUT_REPORTS_DIR, CACHE_DIR]:
        directory.mkdir(parents=True, exist_ok=True)


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("lab4")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
    file_handler = logging.FileHandler(OUTPUT_LOGS_DIR / "lab4.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)
    return logger


def normalize_whitespace(value: str) -> str:
    cleaned = value.replace("\xa0", " ")
    cleaned = cleaned.replace("\u200b", "")
    cleaned = WHITESPACE_RE.sub(" ", cleaned)
    return cleaned.strip()


def parse_interval_text(text: str) -> Interval | None:
    match = INTERVAL_RE.match(normalize_whitespace(text))
    if not match:
        return None
    start = int(match.group(1).replace(" ", ""))
    end = int(match.group(2).replace(" ", ""))
    return Interval(start=start, end=end)


def extract_doc_number_from_url(url: str) -> str:
    query = parse_qs(urlparse(url).query)
    return query.get("DocNumber", [""])[0]


def absolute_url(href: str) -> str:
    return urljoin(BASE_URL, href)


def registry_url(href: str) -> str:
    return urljoin(REGISTERS_ROOT_URL, href)


def save_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def first_date(value: str) -> str | None:
    match = DATE_RE.search(value)
    return match.group(1) if match else None


def ddmmyyyy_to_iso(value: str | None) -> str | None:
    if not value:
        return None
    return datetime.strptime(value, "%d.%m.%Y").date().isoformat()


def text_without_label(value: str, label: str) -> str:
    cleaned = normalize_whitespace(value)
    return normalize_whitespace(cleaned.replace(label, "", 1)) if cleaned.startswith(label) else cleaned


def parse_people_block(paragraph: Tag | None) -> list[str]:
    if paragraph is None:
        return []
    bold = paragraph.find("b")
    if not bold:
        return []
    items: list[str] = []
    for raw_line in bold.get_text("\n", strip=True).splitlines():
        line = normalize_whitespace(raw_line.strip(" ,;"))
        if line:
            items.append(line)
    return items


def find_paragraph_by_prefix(container: Tag | BeautifulSoup, prefix: str) -> Tag | None:
    for paragraph in container.find_all("p"):
        text = normalize_whitespace(paragraph.get_text(" ", strip=True))
        if text.startswith(prefix):
            return paragraph
    return None


def extract_between_anchors(soup: BeautifulSoup, start_href: str, end_href: str) -> list[str]:
    start_anchor = soup.find("a", href=start_href)
    end_anchor = soup.find("a", href=end_href)
    if start_anchor is None or end_anchor is None:
        return []

    parts: list[str] = []
    for element in start_anchor.next_elements:
        if element == end_anchor:
            break
        if isinstance(element, Tag) and element.name == "p":
            text = normalize_whitespace(element.get_text(" ", strip=True))
            if text:
                parts.append(text)
    return parts


def split_description_sections(paragraphs: list[str]) -> list[dict[str, str]]:
    if not paragraphs:
        return []

    sections: list[dict[str, str]] = []
    current_title = "Описание"
    current_paragraphs: list[str] = []
    section_number = 1

    for paragraph in paragraphs:
        is_heading = paragraph == paragraph.upper() and len(paragraph) > 4 and not paragraph.startswith("[")
        if is_heading:
            if current_paragraphs:
                sections.append(
                    {
                        "num": str(section_number),
                        "title": current_title,
                        "text": "\n".join(current_paragraphs).strip(),
                    }
                )
                section_number += 1
                current_paragraphs = []
            current_title = paragraph
            continue
        current_paragraphs.append(paragraph)

    if current_paragraphs:
        sections.append(
            {
                "num": str(section_number),
                "title": current_title,
                "text": "\n".join(current_paragraphs).strip(),
            }
        )

    return sections


def parse_classification_items_ipc(soup: BeautifulSoup) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for item in soup.select("ul.ipc li a"):
        raw_text = normalize_whitespace(item.get_text(" ", strip=True))
        version_match = re.search(r"\(([^)]+)\)", raw_text)
        code = normalize_whitespace(raw_text.split("(")[0])
        if code:
            items.append({"code": code, "version": version_match.group(1) if version_match else ""})
    return items


def parse_classification_items_cpc(soup: BeautifulSoup) -> list[dict[str, str]]:
    spk_cell = soup.find("td", class_="spk")
    if spk_cell is None:
        return []

    items: list[dict[str, str]] = []
    for italic in spk_cell.find_all("i"):
        bold = italic.find("b")
        if bold is None:
            continue
        code = normalize_whitespace(bold.get_text(" ", strip=True))
        version_match = re.search(r"\(([^)]+)\)", italic.get_text(" ", strip=True))
        items.append({"code": code, "version": version_match.group(1) if version_match else ""})
    return items


def parse_status_info(soup: BeautifulSoup) -> dict[str, str | None]:
    status_row = soup.select_one("table.Status tr td.StatusR")
    fee_row = soup.select("table.Status tr td.StatusR")
    status_text = normalize_whitespace(status_row.get_text(" ", strip=True)) if status_row else ""
    match = STATUS_RE.match(status_text)
    fee_text = normalize_whitespace(fee_row[1].get_text(" ", strip=True)) if len(fee_row) > 1 else None
    if match:
        return {
            "status": normalize_whitespace(match.group("status")),
            "last_change": ddmmyyyy_to_iso(match.group("date")),
            "accrual_info": fee_text,
        }
    return {"status": status_text or None, "last_change": None, "accrual_info": fee_text}


def parse_top_metadata(soup: BeautifulSoup) -> dict[str, str]:
    def text_by_id(element_id: str) -> str:
        node = soup.find(id=element_id)
        return normalize_whitespace(node.get_text(" ", strip=True)) if node is not None else ""

    country = text_by_id("top2")
    number = text_by_id("top4")
    kind = text_by_id("top6")
    return {"country": country, "number": number, "kind": kind}


def paragraph_text(paragraph: Tag | None) -> str | None:
    if paragraph is None:
        return None
    return normalize_whitespace(paragraph.get_text(" ", strip=True))


class PatentPageParser:
    def parse(self, html: str, url: str, registry: RegistryConfig) -> dict[str, Any] | None:
        soup = BeautifulSoup(html, "html.parser")
        if soup.find(id="B542") is None or soup.find(id="bib") is None:
            return None

        top_meta = parse_top_metadata(soup)
        bib = soup.find(id="bib")
        assert bib is not None

        application_paragraph = find_paragraph_by_prefix(bib, "(21)(22) Заявка:")
        registration_paragraph = find_paragraph_by_prefix(bib, "Дата регистрации:")
        application_publication_paragraph = find_paragraph_by_prefix(bib, "(43) Дата публикации заявки:")
        publication_paragraph = find_paragraph_by_prefix(bib, "(45) Опубликовано:")
        search_report_paragraph = find_paragraph_by_prefix(bib, "(56) Список документов")
        correspondence_paragraph = find_paragraph_by_prefix(bib, "Адрес для переписки:")
        authors_paragraph = find_paragraph_by_prefix(bib, "(72) Автор(ы):")
        owners_paragraph = find_paragraph_by_prefix(bib, "(73) Патентообладатель(и):")

        application_number = None
        application_date = None
        application_url = None
        if application_paragraph is not None:
            application_link = application_paragraph.find("a")
            application_url = absolute_url(application_link["href"]) if application_link and application_link.get("href") else None
            application_bold = application_paragraph.find("b")
            application_text = normalize_whitespace(application_bold.get_text(" ", strip=True)) if application_bold else ""
            number_match = re.match(r"([^,]+),\s*(\d{2}\.\d{2}\.\d{4})", application_text)
            if number_match:
                application_number = normalize_whitespace(number_match.group(1))
                application_date = ddmmyyyy_to_iso(number_match.group(2))

        publication_date = None
        publication_bulletin_number = None
        official_publication_pdf_url = None
        if publication_paragraph is not None:
            bolds = publication_paragraph.find_all("b")
            if bolds:
                publication_date = ddmmyyyy_to_iso(first_date(bolds[0].get_text(" ", strip=True)))
                publication_link = bolds[0].find("a")
                if publication_link and publication_link.get("href"):
                    official_publication_pdf_url = absolute_url(publication_link["href"])
            if len(bolds) > 1:
                publication_bulletin_number = normalize_whitespace(bolds[1].get_text(" ", strip=True))

        application_publication_date = None
        application_publication_bulletin = None
        if application_publication_paragraph is not None:
            bolds = application_publication_paragraph.find_all("b")
            if bolds:
                application_publication_date = ddmmyyyy_to_iso(first_date(bolds[0].get_text(" ", strip=True)))
            if len(bolds) > 1:
                application_publication_bulletin = normalize_whitespace(bolds[1].get_text(" ", strip=True))

        registration_date = None
        if registration_paragraph is not None:
            registration_bold = registration_paragraph.find("b")
            registration_date = ddmmyyyy_to_iso(
                first_date(registration_bold.get_text(" ", strip=True) if registration_bold else "")
            )

        abstract_text = ""
        abstract_node = soup.find(id="Abs")
        if abstract_node is not None:
            abstract_text = text_without_label(abstract_node.get_text(" ", strip=True), "(57) Реферат:")

        title_text = ""
        title_node = soup.find(id="B542")
        if title_node is not None:
            title_text = text_without_label(title_node.get_text(" ", strip=True), "(54)")

        description_paragraphs = extract_between_anchors(soup, "DeStart", "DeEnd")
        claims_paragraphs = extract_between_anchors(soup, "ClStart", "ClEnd")

        document_number = extract_doc_number_from_url(url)

        return {
            "patent_id": document_number,
            "patent_type": registry.patent_type,
            "patent_type_ru": registry.patent_type_ru,
            "registry_title": registry.title,
            "patent_number_full": " ".join(
                part for part in [top_meta["country"], top_meta["number"], top_meta["kind"]] if part
            ),
            "status_info": parse_status_info(soup),
            "application_details": {
                "application_number": application_number,
                "application_date": application_date,
                "registration_date": registration_date,
                "publication_date": publication_date,
                "publication_bulletin_number": publication_bulletin_number,
                "application_publication_date": application_publication_date,
                "application_publication_bulletin_number": application_publication_bulletin,
                "application_url": application_url,
                "official_publication_pdf_url": official_publication_pdf_url,
            },
            "ipc": parse_classification_items_ipc(soup),
            "cpc": parse_classification_items_cpc(soup),
            "inventors": parse_people_block(authors_paragraph),
            "owners": parse_people_block(owners_paragraph),
            "correspondence_address": text_without_label(
                paragraph_text(correspondence_paragraph) or "", "Адрес для переписки:"
            )
            or None,
            "abstract": abstract_text or None,
            "claims": "\n".join(claims_paragraphs).strip() or None,
            "description_sections": split_description_sections(description_paragraphs),
            "search_report": text_without_label(
                paragraph_text(search_report_paragraph) or "", "(56) Список документов, цитированных в отчете о поиске:"
            )
            or None,
            "title": title_text,
            "url": url,
            "parsed_at": datetime.now().isoformat(timespec="seconds"),
        }


class FipsNavigator:
    def __init__(self, *, headless: bool, tree_delay: float, logger: logging.Logger) -> None:
        self.logger = logger
        self.tree_delay = tree_delay
        self.driver = self._build_driver(headless=headless)
        self.http_session: Session = requests.Session()
        self.base_cookies: dict[str, str] = {}

    def _build_driver(self, *, headless: bool) -> webdriver.Chrome:
        options = Options()
        chrome_binary = shutil.which("google-chrome") or shutil.which("chrome") or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if Path(chrome_binary).exists():
            options.binary_location = chrome_binary
        if headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-gpu")
        options.add_argument("--disable-dev-shm-usage")
        return webdriver.Chrome(options=options)

    def close(self) -> None:
        self.driver.quit()

    def collect_document_links(
        self,
        registry: RegistryConfig,
        target_interval: Interval,
        *,
        limit: int | None = None,
    ) -> list[dict[str, str]]:
        self.logger.info("Сканирую дерево диапазонов: %s | %s", registry.title, target_interval.label)
        collected: list[dict[str, str]] = []
        self._open_registry_from_root(registry)
        self._sync_driver_cookies_to_http_session()
        start_url, start_html = self._navigate_to_target_interval_http(
            current_url=self.driver.current_url,
            current_html=self.driver.page_source,
            target_interval=target_interval,
        )
        self._crawl_http_page(
            current_url=start_url,
            current_html=start_html,
            target_interval=target_interval,
            collected=collected,
            limit=limit,
            visited_urls=set(),
        )
        deduplicated = {item["doc_number"]: item for item in collected}
        return [deduplicated[key] for key in sorted(deduplicated, key=int)]

    def _open_registry_from_root(self, registry: RegistryConfig) -> None:
        self.driver.get(REGISTERS_ROOT_URL)
        WebDriverWait(self.driver, 20).until(lambda d: registry.title in d.page_source)
        previous_url = self.driver.current_url
        self.driver.find_element(By.LINK_TEXT, registry.title).click()
        WebDriverWait(self.driver, 20).until(lambda d: d.current_url != previous_url)
        self._wait_for_registry_content()
        self.logger.info("Открыт раздел %s -> %s", registry.title, self.driver.current_url)

    def _wait_for_registry_content(self) -> None:
        WebDriverWait(self.driver, 20).until(
            lambda d: "ВЫБЕРИТЕ ДИАПАЗОН НОМЕРОВ" in d.page_source.upper() or "ДИАПАЗОН:" in d.page_source.upper()
        )
        time.sleep(self.tree_delay)

    def _sync_driver_cookies_to_http_session(self) -> None:
        self.http_session.cookies.clear()
        for cookie in self.driver.get_cookies():
            self.http_session.cookies.set(cookie["name"], cookie["value"])
        self.base_cookies = requests.utils.dict_from_cookiejar(self.http_session.cookies)

    def _fetch_registry_page(self, url: str) -> str:
        response = self.http_session.get(url, timeout=DEFAULT_REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.text

    @staticmethod
    def _content_text_for(driver: webdriver.Chrome) -> str:
        elements = driver.find_elements(By.ID, "mainpagecontent")
        if elements:
            return elements[0].text
        return driver.page_source

    def _wait_for_transition(self, *, previous_url: str, previous_content: str, target_url: str | None = None) -> None:
        WebDriverWait(self.driver, 20).until(
            lambda d: (
                (target_url is not None and d.current_url == target_url)
                or d.current_url != previous_url
                or self._content_text_for(d) != previous_content
            )
        )
        WebDriverWait(self.driver, 20).until(lambda d: self._content_text_for(d) != previous_content)
        self._wait_for_registry_content()

    def _navigate_to_target_interval(self, target_interval: Interval) -> None:
        for _ in range(12):
            soup = BeautifulSoup(self.driver.page_source, "html.parser")
            list_interval = self._extract_list_page_interval(soup)
            if list_interval == target_interval:
                return

            current_interval = self._extract_selected_interval(soup)
            if current_interval == target_interval:
                return

            candidates = [
                item
                for item in self._extract_visible_range_links(soup)
                if item["interval"].contains(target_interval)
            ]
            if not candidates:
                raise RuntimeError(f"Не удалось найти путь до диапазона {target_interval.label}")

            candidates.sort(key=lambda item: (item["interval"].end - item["interval"].start, item["interval"].start))
            next_item = candidates[0]
            self.logger.info("Переход к диапазону %s", next_item["interval"].label)
            self._click_link_by_href(next_item["href"])

        raise RuntimeError(f"Превышена глубина переходов при поиске диапазона {target_interval.label}")

    def _navigate_to_target_interval_http(
        self,
        *,
        current_url: str,
        current_html: str,
        target_interval: Interval,
    ) -> tuple[str, str]:
        for _ in range(12):
            soup = BeautifulSoup(current_html, "html.parser")
            list_interval = self._extract_list_page_interval(soup)
            if list_interval == target_interval:
                return current_url, current_html

            current_interval = self._extract_selected_interval(soup)
            if current_interval == target_interval:
                return current_url, current_html

            candidates = [
                item
                for item in self._extract_visible_range_links(soup)
                if item["interval"].contains(target_interval)
            ]
            if not candidates:
                raise RuntimeError(f"Не удалось найти путь до диапазона {target_interval.label}")

            candidates.sort(key=lambda item: (item["interval"].end - item["interval"].start, item["interval"].start))
            next_item = candidates[0]
            current_url = registry_url(next_item["href"])
            self.logger.info("Переход к диапазону %s", next_item["interval"].label)
            current_html = self._fetch_registry_page(current_url)

        raise RuntimeError(f"Превышена глубина переходов при поиске диапазона {target_interval.label}")

    def _crawl_http_page(
        self,
        *,
        current_url: str,
        current_html: str,
        target_interval: Interval,
        collected: list[dict[str, str]],
        limit: int | None,
        visited_urls: set[str],
    ) -> None:
        if limit is not None and len(collected) >= limit:
            return
        if current_url in visited_urls:
            return
        visited_urls.add(current_url)

        soup = BeautifulSoup(current_html, "html.parser")
        list_interval = self._extract_list_page_interval(soup)
        document_links = self._extract_document_links_from_list_page(soup)
        if list_interval is not None:
            self.logger.info(
                "Страница списка %s: найдено %s ссылок на документы",
                list_interval.label,
                len(document_links),
            )
        if document_links and list_interval and list_interval.overlaps(target_interval):
            for item in document_links:
                if limit is not None and len(collected) >= limit:
                    break
                collected.append(item)
            self.logger.info(
                "Найден терминальный диапазон %s (%s документов, накоплено %s)",
                list_interval.label,
                len(document_links),
                len(collected),
            )
            return

        current_interval, child_links = self._extract_child_range_links(soup)
        if not child_links:
            self.logger.warning("Не удалось разобрать дочерние диапазоны для %s", current_url)
            return

        relevant_children = [item for item in child_links if item["interval"].overlaps(target_interval)]
        if current_interval:
            self.logger.info(
                "Диапазон %s -> дочерних узлов: %s, релевантных: %s",
                current_interval.label,
                len(child_links),
                len(relevant_children),
            )

        for item in relevant_children:
            if limit is not None and len(collected) >= limit:
                break
            self.logger.info("Открываю дочерний диапазон %s", item["interval"].label)
            next_url = registry_url(item["href"])
            next_html = self._fetch_registry_page(next_url)
            self._crawl_http_page(
                current_url=next_url,
                current_html=next_html,
                target_interval=target_interval,
                collected=collected,
                limit=limit,
                visited_urls=visited_urls,
            )

    def _crawl_current_page(
        self,
        *,
        registry: RegistryConfig,
        target_interval: Interval,
        collected: list[dict[str, str]],
        limit: int | None,
    ) -> None:
        if limit is not None and len(collected) >= limit:
            return

        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        list_interval = self._extract_list_page_interval(soup)
        document_links = self._extract_document_links_from_list_page(soup)
        if list_interval is not None:
            self.logger.info(
                "Страница списка %s: найдено %s ссылок на документы",
                list_interval.label,
                len(document_links),
            )
        if document_links:
            if list_interval and list_interval.overlaps(target_interval):
                for item in document_links:
                    if limit is not None and len(collected) >= limit:
                        break
                    collected.append(item)
                self.logger.info(
                    "Найден терминальный диапазон %s (%s документов, накоплено %s)",
                    list_interval.label if list_interval else "неизвестно",
                    len(document_links),
                    len(collected),
                )
            return

        current_interval, child_links = self._extract_child_range_links(soup)
        if not child_links:
            self.logger.warning("Не удалось разобрать дочерние диапазоны для %s", self.driver.current_url)
            return

        relevant_children = [item for item in child_links if item["interval"].overlaps(target_interval)]
        if current_interval:
            self.logger.info(
                "Диапазон %s -> дочерних узлов: %s, релевантных: %s",
                current_interval.label,
                len(child_links),
                len(relevant_children),
            )

        for item in relevant_children:
            if limit is not None and len(collected) >= limit:
                break
            self.logger.info("Открываю дочерний диапазон %s", item["interval"].label)
            self._click_link_by_href(item["href"])
            self._crawl_current_page(
                registry=registry,
                target_interval=target_interval,
                collected=collected,
                limit=limit,
            )
            if limit is not None and len(collected) >= limit:
                break
            previous_url = self.driver.current_url
            previous_content = self._content_text_for(self.driver)
            self.driver.back()
            self._wait_for_transition(previous_url=previous_url, previous_content=previous_content)

    def _click_link_by_href(self, href: str) -> None:
        css_selector = f'a[href="{href}"]'
        previous_url = self.driver.current_url
        previous_content = self._content_text_for(self.driver)
        target_url = registry_url(href)
        for element in self.driver.find_elements(By.CSS_SELECTOR, css_selector):
            if normalize_whitespace(element.text):
                self.driver.execute_script("arguments[0].click();", element)
                self._wait_for_transition(
                    previous_url=previous_url,
                    previous_content=previous_content,
                    target_url=target_url,
                )
                self.logger.info("После клика открыт URL: %s", self.driver.current_url)
                return
        raise RuntimeError(f"Не удалось нажать ссылку {href}")

    def _extract_list_page_interval(self, soup: BeautifulSoup) -> Interval | None:
        content = soup.find(id="mainpagecontent")
        if content is None:
            return None
        text = normalize_whitespace(content.get_text(" ", strip=True))
        match = re.search(r"диапазон:\s*([0-9 ]+\s*-\s*[0-9 ]+)", text, flags=re.IGNORECASE)
        return parse_interval_text(match.group(1)) if match else None

    def _extract_selected_interval(self, soup: BeautifulSoup) -> Interval | None:
        tree_root = soup.select_one("#mainpagecontent .list_ul > ul.parentnode")
        if tree_root is None:
            return None

        selected_links = [
            anchor
            for anchor in tree_root.select("a.red")
            if parse_interval_text(anchor.get_text(" ", strip=True)) is not None
        ]
        if not selected_links:
            return None
        return parse_interval_text(selected_links[-1].get_text(" ", strip=True))

    def _extract_visible_range_links(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        content = soup.find(id="mainpagecontent")
        if content is None:
            return []

        seen: set[tuple[int, int, str]] = set()
        items: list[dict[str, Any]] = []
        for anchor in content.find_all("a", href=True):
            interval = parse_interval_text(anchor.get_text(" ", strip=True))
            if interval is None:
                continue
            key = (interval.start, interval.end, anchor["href"])
            if key in seen:
                continue
            seen.add(key)
            items.append({"interval": interval, "href": anchor["href"]})
        return items

    def _extract_document_links_from_list_page(self, soup: BeautifulSoup) -> list[dict[str, str]]:
        content = soup.find(id="mainpagecontent")
        if content is None:
            return []

        results: list[dict[str, str]] = []
        seen: set[str] = set()
        for anchor in content.find_all("a", href=True):
            href = anchor["href"]
            if "registers-doc-view/fips_servlet" not in href:
                continue
            if "TypeFile=html" not in href:
                continue
            url = absolute_url(href)
            doc_number = extract_doc_number_from_url(url)
            if not doc_number or doc_number in seen:
                continue
            seen.add(doc_number)
            results.append({"doc_number": doc_number, "url": url})
        return results

    def _extract_child_range_links(self, soup: BeautifulSoup) -> tuple[Interval | None, list[dict[str, Any]]]:
        tree_root = soup.select_one("#mainpagecontent .list_ul > ul.parentnode")
        if tree_root is None:
            return None, []

        selected_links = [
            anchor
            for anchor in tree_root.select("a.red")
            if parse_interval_text(anchor.get_text(" ", strip=True)) is not None
        ]
        if not selected_links:
            return None, []

        current_link = selected_links[-1]
        current_interval = parse_interval_text(current_link.get_text(" ", strip=True))
        current_li = current_link.find_parent("li")
        if current_li is None:
            return current_interval, []

        child_ul = current_li.find_next_sibling("ul")
        if child_ul is None:
            return current_interval, []

        child_links: list[dict[str, Any]] = []
        for child_li in child_ul.find_all("li", recursive=False):
            anchors = child_li.find_all("a", href=True, recursive=False)
            if not anchors:
                continue
            link = anchors[-1]
            interval = parse_interval_text(link.get_text(" ", strip=True))
            if interval is None:
                continue
            child_links.append({"interval": interval, "href": link["href"]})
        return current_interval, child_links


class PatentFetcher:
    def __init__(
        self,
        *,
        timeout: int,
        doc_delay: float,
        use_cache: bool,
        logger: logging.Logger,
    ) -> None:
        self.timeout = timeout
        self.doc_delay = doc_delay
        self.use_cache = use_cache
        self.logger = logger
        self.page_parser = PatentPageParser()
        self._thread_local = local()

    def _session(self) -> Session:
        session = getattr(self._thread_local, "session", None)
        if session is None:
            session = requests.Session()
            adapter = requests.adapters.HTTPAdapter(pool_connections=DEFAULT_WORKERS * 2, pool_maxsize=DEFAULT_WORKERS * 2)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            self._thread_local.session = session
        return session

    def fetch(self, url: str, registry: RegistryConfig) -> dict[str, Any] | None:
        doc_number = extract_doc_number_from_url(url)
        cache_path = CACHE_DIR / registry.slug / f"{doc_number}.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)

        if self.use_cache and cache_path.exists():
            return load_json(cache_path, None)

        response = self._session().get(url, timeout=self.timeout)
        response.raise_for_status()
        html = response.content.decode("cp1251", errors="ignore")
        if DAILY_DOC_LIMIT_TEXT in html:
            raise DailyViewLimitExceededError(
                "ФИПС сообщил о превышении дневного лимита просмотров документов. Продолжить выгрузку можно на следующий день с флагом --resume."
            )
        record = self.page_parser.parse(html, url, registry)
        time.sleep(self.doc_delay)

        if record is not None:
            save_json(cache_path, record)
        return record


def build_summary_dataframe(records: list[dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for item in records:
        rows.append(
            {
                "patent_id": item.get("patent_id"),
                "registry": item.get("registry_title"),
                "patent_type": item.get("patent_type"),
                "title": item.get("title"),
                "registration_date": item.get("application_details", {}).get("registration_date"),
                "publication_date": item.get("application_details", {}).get("publication_date"),
                "application_number": item.get("application_details", {}).get("application_number"),
                "status": item.get("status_info", {}).get("status"),
                "inventors_count": len(item.get("inventors", [])),
                "owners_count": len(item.get("owners", [])),
                "ipc_codes": "; ".join(entry["code"] for entry in item.get("ipc", [])),
                "cpc_codes": "; ".join(entry["code"] for entry in item.get("cpc", [])),
                "url": item.get("url"),
            }
        )
    return pd.DataFrame(rows)


def save_registry_outputs(
    *,
    variant: int,
    registry: RegistryConfig,
    records: list[dict[str, Any]],
) -> dict[str, Path]:
    json_path = OUTPUT_DATA_DIR / f"variant_{variant}_{registry.slug}.json"
    csv_path = OUTPUT_DATA_DIR / f"variant_{variant}_{registry.slug}_summary.csv"
    save_json(json_path, records)
    build_summary_dataframe(records).to_csv(csv_path, index=False, encoding="utf-8")
    return {"json": json_path, "csv": csv_path}


def build_status_table(records: list[dict[str, Any]]) -> pd.DataFrame:
    counter = Counter(item.get("status_info", {}).get("status") or "не указан" for item in records)
    return pd.DataFrame(sorted(counter.items()), columns=["status", "count"])


def collect_records(
    *,
    document_links: list[dict[str, str]],
    existing_by_id: dict[str, dict[str, Any]],
    registry: RegistryConfig,
    fetcher: PatentFetcher,
    resume: bool,
    workers: int,
    flush_every: int,
    interim_json_path: Path,
    logger: logging.Logger,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = list(existing_by_id.values())
    pending_links = [
        item for item in document_links if not (resume and item["doc_number"] in existing_by_id)
    ]
    logger.info(
        "%s: к загрузке %s карточек (%s уже есть в промежуточном JSON)",
        registry.title,
        len(pending_links),
        len(existing_by_id),
    )

    if not pending_links:
        return records

    processed = 0
    flush_every = max(flush_every, 1)

    if workers <= 1:
        for item in pending_links:
            doc_number = item["doc_number"]
            logger.info("Загружаю %s | %s", registry.title, doc_number)
            try:
                record = fetcher.fetch(item["url"], registry)
            except DailyViewLimitExceededError:
                flush_intermediate_records(interim_json_path, records)
                raise
            except Exception:
                logger.exception("Ошибка при загрузке карточки %s", doc_number)
                continue
            processed += 1
            if record is None:
                logger.warning("Не удалось разобрать карточку %s", doc_number)
                continue
            records.append(record)
            if processed % flush_every == 0:
                flush_intermediate_records(interim_json_path, records)
        return records

    quota_reached = False
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_item = {
            executor.submit(fetcher.fetch, item["url"], registry): item
            for item in pending_links
        }
        for future in as_completed(future_to_item):
            item = future_to_item[future]
            doc_number = item["doc_number"]
            processed += 1
            try:
                record = future.result()
            except DailyViewLimitExceededError:
                quota_reached = True
                logger.error(
                    "ФИПС остановил выдачу документов по дневной квоте. Сохраняю прогресс и завершаю текущий прогон."
                )
                flush_intermediate_records(interim_json_path, records)
                executor.shutdown(wait=False, cancel_futures=True)
                break
            except Exception:
                logger.exception("Ошибка при загрузке карточки %s", doc_number)
                continue

            if record is None:
                logger.warning("Не удалось разобрать карточку %s", doc_number)
                continue

            records.append(record)
            if processed % flush_every == 0:
                logger.info(
                    "%s: обработано %s/%s карточек",
                    registry.title,
                    processed,
                    len(pending_links),
                )
                flush_intermediate_records(interim_json_path, records)
    if quota_reached:
        raise DailyViewLimitExceededError(
            "ФИПС сообщил о превышении дневного лимита просмотров документов. Продолжить выгрузку можно на следующий день с флагом --resume."
        )
    return records


def detect_hadoop_environment() -> dict[str, Any]:
    local_hadoop_bin = LOCAL_HADOOP_HOME / "bin" / "hadoop"
    local_hdfs_bin = LOCAL_HADOOP_HOME / "bin" / "hdfs"
    return {
        "java_present": shutil.which("java") is not None,
        "hadoop_present": shutil.which("hadoop") is not None or local_hadoop_bin.exists(),
        "hdfs_present": shutil.which("hdfs") is not None or local_hdfs_bin.exists(),
        "hadoop_home": str(LOCAL_HADOOP_HOME) if local_hadoop_bin.exists() else None,
        "spark_present": shutil.which("spark-submit") is not None,
    }


def render_report(
    *,
    variant: int,
    selected_registries: list[str],
    records_by_registry: dict[str, list[dict[str, Any]]],
    output_paths: dict[str, dict[str, Path]],
    environment_info: dict[str, Any],
    args: argparse.Namespace,
) -> None:
    total_records = sum(len(items) for items in records_by_registry.values())
    report_lines = [
        "# Отчёт по лабораторной работе №4",
        "",
        "## Тема",
        "",
        "Создание базы знаний на основе открытых ресурсов ФИПС с использованием Selenium, BeautifulSoup4, Pandas и подготовкой данных для Hadoop.",
        "",
        "## Входные параметры запуска",
        "",
        f"- Вариант: `{variant}`",
        f"- Разделы: `{', '.join(selected_registries)}`",
        f"- Ограничение по числу документов на раздел: `{args.limit if args.limit is not None else 'без ограничения'}`",
        f"- Режим возобновления: `{args.resume}`",
        f"- Использование кэша: `{not args.no_cache}`",
        f"- Число потоков загрузки карточек: `{args.workers}`",
        "",
        "## Что делает программа",
        "",
        "1. Открывает реестр ФИПС в Selenium и проходит по дереву диапазонов номеров.",
        "2. Доходит до конечных интервалов по 100 документов и собирает HTML-ссылки карточек.",
        "3. Загружает карточки документов через requests и BeautifulSoup4.",
        "4. Нормализует поля в единый JSON-формат и сохраняет результаты.",
        "5. Формирует Pandas-таблицы для краткой сводки и отчётных CSV.",
        "",
        "## Результаты текущего прогона",
        "",
        f"- Всего собранных записей: `{total_records}`",
    ]

    for registry_slug in selected_registries:
        registry = REGISTRIES[registry_slug]
        records = records_by_registry.get(registry_slug, [])
        paths = output_paths.get(registry_slug, {})
        report_lines.extend(
            [
                f"- `{registry.title}`: `{len(records)}` записей",
                f"- JSON: `{paths.get('json', '')}`",
                f"- CSV: `{paths.get('csv', '')}`",
            ]
        )

    report_lines.extend(
        [
            "",
            "## Пример структуры данных",
            "",
            "Каждая запись содержит:",
            "",
            "- `patent_id`, `patent_type`, `patent_number_full`, `title`",
            "- `status_info`",
            "- `application_details`",
            "- `ipc`, `cpc`",
            "- `inventors`, `owners`, `correspondence_address`",
            "- `abstract`, `claims`, `description_sections`, `search_report`",
            "- `url`",
            "",
            "## Hadoop",
            "",
            f"- Java в системе: `{environment_info['java_present']}`",
            f"- Hadoop в системе: `{environment_info['hadoop_present']}`",
            f"- HDFS-клиент доступен: `{environment_info['hdfs_present']}`",
            f"- Spark в системе: `{environment_info['spark_present']}`",
            f"- Локальный Hadoop Home: `{environment_info['hadoop_home'] or 'не найден'}`",
            "",
            "Для части с Hadoop подготовлены команды загрузки JSON в HDFS и краткий сценарий проверки в файле `hadoop_report.md`.",
            "",
            "## Вывод",
            "",
            "Код лабораторной реализует обязательные технологии Selenium, BeautifulSoup4 и Pandas, а также формирует итоговые JSON/CSV-артефакты для последующей загрузки в Hadoop.",
        ]
    )

    REPORT_FILE.write_text("\n".join(report_lines), encoding="utf-8")


def render_hadoop_report(
    *,
    variant: int,
    output_paths: dict[str, dict[str, Path]],
    environment_info: dict[str, Any],
) -> None:
    combined_candidate = OUTPUT_DATA_DIR / f"variant_{variant}_patents.json"
    combined_hdfs_target = f"/user/student/patents/variant_{variant}_patents.json"

    lines = [
        "# Краткий отчёт по Hadoop",
        "",
        "## Состояние текущей среды",
        "",
        f"- Java доступна: `{environment_info['java_present']}`",
        f"- Hadoop установлен: `{environment_info['hadoop_present']}`",
        f"- HDFS-клиент доступен: `{environment_info['hdfs_present']}`",
        f"- Spark установлен: `{environment_info['spark_present']}`",
        f"- Локальный Hadoop Home: `{environment_info['hadoop_home'] or 'не найден'}`",
        "",
        "## Рекомендуемая версия",
        "",
        "`Hadoop 3.4.2`",
        "",
        "## Подготовленный файл для HDFS",
        "",
        f"- Основной JSON: `{combined_candidate}`",
        "",
        "## Команды для загрузки в HDFS",
        "",
        "```bash",
        "hdfs dfs -mkdir -p /user/student/patents",
        f"hdfs dfs -put {combined_candidate} {combined_hdfs_target}",
        "hdfs dfs -ls /user/student/patents",
        "```",
        "",
        "## Что проверить после загрузки",
        "",
        "1. Файл появился в `/user/student/patents`.",
        "2. Размер файла в HDFS совпадает с локальным.",
        "3. JSON корректно читается из HDFS-команд и/или Spark.",
        "",
        "## Пример чтения в Spark",
        "",
        "```python",
        "df = spark.read.json('/user/student/patents/variant_1_patents.json')",
        "df.printSchema()",
        "df.select('patent_id', 'title', 'status_info.status').show(10, truncate=False)",
        "```",
        "",
        "## Примечание",
        "",
        "В проекте подготовлена локальная установка Hadoop 3.4.2 и итоговый JSON для загрузки в HDFS. После запуска `start_hadoop.sh` команды из раздела выше можно выполнять без дополнительной настройки путей.",
    ]
    HADOOP_REPORT_FILE.write_text("\n".join(lines), encoding="utf-8")


def combine_registry_outputs(variant: int, records_by_registry: dict[str, list[dict[str, Any]]]) -> Path:
    combined: list[dict[str, Any]] = []
    for registry_slug in ["inventions", "utility_models"]:
        combined.extend(records_by_registry.get(registry_slug, []))

    combined_path = OUTPUT_DATA_DIR / f"variant_{variant}_patents.json"
    save_json(combined_path, combined)
    return combined_path


def flush_intermediate_records(path: Path, records: list[dict[str, Any]]) -> None:
    save_json(path, records)


def should_reuse_links_manifest(links_json_path: Path, links_meta_path: Path, limit: int | None) -> bool:
    if not links_json_path.exists() or not links_meta_path.exists():
        return False

    metadata = load_json(links_meta_path, {})
    saved_limit = metadata.get("limit")
    if limit is None:
        return saved_limit is None
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Лабораторная работа 4: сбор базы знаний по ФИПС.")
    parser.add_argument("--variant", type=int, default=1, choices=sorted(VARIANT_RANGES), help="Номер варианта из таблицы.")
    parser.add_argument(
        "--registry",
        choices=["all", *REGISTRIES.keys()],
        default="all",
        help="Какой раздел парсить: оба (`all`) или только один.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Лимит документов на раздел для тестового запуска.")
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Продолжить с использованием уже собранного JSON и кэша.",
    )
    parser.add_argument(
        "--headless",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Запуск Chrome в headless-режиме.",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Не использовать локальный кэш карточек документов.",
    )
    parser.add_argument(
        "--links-only",
        action="store_true",
        help="Только собрать и сохранить список ссылок на карточки, не открывая сами документы.",
    )
    parser.add_argument(
        "--recollect-links",
        action="store_true",
        help="Пересобрать список ссылок даже если ранее уже был сохранён манифест.",
    )
    parser.add_argument("--tree-delay", type=float, default=DEFAULT_TREE_DELAY, help="Пауза между переходами по дереву диапазонов.")
    parser.add_argument("--doc-delay", type=float, default=DEFAULT_DOC_DELAY, help="Пауза между запросами карточек документов.")
    parser.add_argument("--flush-every", type=int, default=DEFAULT_FLUSH_EVERY, help="Как часто пересохранять промежуточный JSON.")
    parser.add_argument("--timeout", type=int, default=DEFAULT_REQUEST_TIMEOUT, help="Таймаут HTTP-запросов к карточкам документов.")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help="Число потоков для загрузки карточек документов.")
    return parser.parse_args()


def main() -> None:
    ensure_output_dirs()
    args = parse_args()
    logger = setup_logger()

    selected_registries = list(REGISTRIES.keys()) if args.registry == "all" else [args.registry]
    variant_ranges = VARIANT_RANGES[args.variant]
    logger.info("Старт лабораторной 4 | вариант=%s | разделы=%s", args.variant, ", ".join(selected_registries))

    navigator = FipsNavigator(headless=args.headless, tree_delay=args.tree_delay, logger=logger)
    fetcher = PatentFetcher(timeout=args.timeout, doc_delay=args.doc_delay, use_cache=not args.no_cache, logger=logger)

    records_by_registry: dict[str, list[dict[str, Any]]] = {}
    output_paths: dict[str, dict[str, Path]] = {}
    run_notes: list[str] = []

    try:
        for registry_slug in selected_registries:
            registry = REGISTRIES[registry_slug]
            target_interval = variant_ranges[registry_slug]
            interim_json_path = OUTPUT_DATA_DIR / f"variant_{args.variant}_{registry.slug}_interim.json"
            links_json_path = OUTPUT_DATA_DIR / f"variant_{args.variant}_{registry.slug}_links.json"
            links_meta_path = OUTPUT_DATA_DIR / f"variant_{args.variant}_{registry.slug}_links_meta.json"

            existing_records = load_json(interim_json_path, []) if args.resume else []
            existing_by_id = {str(item.get("patent_id")): item for item in existing_records if item.get("patent_id")}

            if (
                args.resume
                and not args.recollect_links
                and should_reuse_links_manifest(links_json_path, links_meta_path, args.limit)
            ):
                document_links = load_json(links_json_path, [])
                logger.info("%s: список ссылок загружен из %s", registry.title, links_json_path)
            else:
                document_links = navigator.collect_document_links(registry, target_interval, limit=args.limit)
                save_json(links_json_path, document_links)
                save_json(
                    links_meta_path,
                    {
                        "variant": args.variant,
                        "registry": registry.slug,
                        "limit": args.limit,
                        "count": len(document_links),
                        "generated_at": datetime.now().isoformat(timespec="seconds"),
                    },
                )
            logger.info("%s: найдено %s ссылок на карточки", registry.title, len(document_links))

            if args.limit is not None:
                document_links = document_links[: args.limit]

            records = list(existing_by_id.values())
            if not args.links_only:
                try:
                    records = collect_records(
                        document_links=document_links,
                        existing_by_id=existing_by_id,
                        registry=registry,
                        fetcher=fetcher,
                        resume=args.resume,
                        workers=args.workers,
                        flush_every=args.flush_every,
                        interim_json_path=interim_json_path,
                        logger=logger,
                    )
                except DailyViewLimitExceededError as exc:
                    logger.error(str(exc))
                    run_notes.append(str(exc))
                    records = load_json(interim_json_path, records)
            else:
                logger.info("%s: режим links-only, карточки не загружаются", registry.title)

            records.sort(key=lambda item: int(item.get("patent_id") or 0))
            flush_intermediate_records(interim_json_path, records)
            output_paths[registry_slug] = save_registry_outputs(variant=args.variant, registry=registry, records=records)
            build_status_table(records).to_csv(
                OUTPUT_DATA_DIR / f"variant_{args.variant}_{registry.slug}_status_counts.csv",
                index=False,
                encoding="utf-8",
            )
            records_by_registry[registry_slug] = records
    finally:
        navigator.close()

    combined_path = combine_registry_outputs(args.variant, records_by_registry)
    environment_info = detect_hadoop_environment()
    render_report(
        variant=args.variant,
        selected_registries=selected_registries,
        records_by_registry=records_by_registry,
        output_paths=output_paths,
        environment_info=environment_info,
        args=args,
    )
    render_hadoop_report(variant=args.variant, output_paths=output_paths, environment_info=environment_info)

    context = {
        "variant": args.variant,
        "selected_registries": selected_registries,
        "records_count": {slug: len(items) for slug, items in records_by_registry.items()},
        "combined_json_path": str(combined_path),
        "report_path": str(REPORT_FILE),
        "hadoop_report_path": str(HADOOP_REPORT_FILE),
        "run_notes": run_notes,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "note": "Если вариант пользователя отличается от 1, достаточно перезапустить main.py с нужным --variant.",
    }
    save_json(COMBINED_REPORT_CONTEXT_FILE, context)

    logger.info("Готово. Общий JSON: %s", combined_path)


if __name__ == "__main__":
    main()
