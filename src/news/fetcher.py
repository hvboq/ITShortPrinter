from __future__ import annotations

import html
import re
import time
import urllib.request
from urllib.parse import urljoin
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime


def _escape_unsupported_xml_entities(xml_text: str) -> str:
    return re.sub(
        r"&(?!amp;|lt;|gt;|apos;|quot;|#[0-9]+;|#x[0-9a-fA-F]+;)",
        "&amp;",
        xml_text,
    )


def _text(element: ET.Element | None, default: str = "") -> str:
    if element is None or element.text is None:
        return default
    return html.unescape(element.text.strip())


def _child_text(element: ET.Element, local_name: str, default: str = "") -> str:
    return _text(element.find(local_name)) or _text(
        element.find(f"{{http://www.w3.org/2005/Atom}}{local_name}"),
        default,
    )


def _parse_date(raw: str) -> str | None:
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).isoformat()
    except Exception:
        return raw


def parse_rss(xml_text: str, source_id: str, source_name: str, source_tier: str, base_url: str = "") -> list[dict]:
    root = ET.fromstring(_escape_unsupported_xml_entities(xml_text))
    items = root.findall(".//item")
    if not items:
        items = root.findall(".//{http://www.w3.org/2005/Atom}entry")

    articles = []
    fetched_at = datetime.now(timezone.utc).isoformat()
    for item in items:
        title = _child_text(item, "title")
        link = _child_text(item, "link")
        if not link:
            atom_link = item.find("{http://www.w3.org/2005/Atom}link")
            link = atom_link.attrib.get("href", "") if atom_link is not None else ""
        if link:
            link = urljoin(base_url, link.strip())
        excerpt = _child_text(item, "description") or _child_text(item, "summary") or _child_text(item, "content")
        published = _child_text(item, "pubDate") or _child_text(item, "published") or _child_text(item, "updated")

        if not title or not link:
            continue

        articles.append(
            {
                "source_id": source_id,
                "source_name": source_name,
                "source_tier": source_tier,
                "language": "unknown",
                "title": title,
                "url": link,
                "canonical_url": link,
                "published_at": _parse_date(published),
                "fetched_at": fetched_at,
                "author": None,
                "raw_excerpt": excerpt,
            }
        )
    return articles


def fetch_rss(url: str, source_id: str, source_name: str, source_tier: str, timeout: int = 20) -> list[dict]:
    request = urllib.request.Request(url, headers={"User-Agent": "PersonalTechNewsBot/0.1 (+local personal use)"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        xml_text = response.read().decode("utf-8", errors="replace")
    time.sleep(1)
    return parse_rss(xml_text, source_id=source_id, source_name=source_name, source_tier=source_tier, base_url=url)
