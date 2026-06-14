import json
import html
import re
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from email.utils import parsedate_to_datetime
from typing import Optional
from urllib.parse import urljoin
from urllib.parse import urlparse
from xml.etree import ElementTree

import requests

from cache import get_processed_news_urls
from cache import save_latest_news_candidates
from config import get_default_text_model
from config import get_news_pipeline_config
from config import get_ollama_model
from llm_provider import generate_text
from status import info
from status import warning


@dataclass
class NewsArticle:
    source: str
    url: str
    title: str
    published_at: str
    summary: str
    content: str
    score: int
    public_interest_score: int = 0
    realism_score: int = 0
    llm_score: int = 0
    keyword_score: int = 0
    score_reason: str = ""
    image_url: str = ""
    category: str = ""


class NewsPipeline:
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    SOURCE_CONFIG = {
        "theverge": {
            "homepage": "https://www.theverge.com/",
            "rss": "https://www.theverge.com/rss/index.xml",
            "seed_urls": [],
            "allowed_domains": {"www.theverge.com", "theverge.com"},
        },
        "zdnet_korea": {
            "homepage": "https://zdnet.co.kr/",
            "rss": "",
            "seed_urls": [],
            "allowed_domains": {"zdnet.co.kr", "www.zdnet.co.kr"},
        },
        "bloter": {
            "homepage": "https://www.bloter.net/",
            "rss": "",
            "seed_urls": [
                "https://www.bloter.net/news/articleList.html?sc_section_code=S1N4&view_type=sm",
                "https://www.bloter.net/news/articleList.html?sc_section_code=S1N20&view_type=sm",
            ],
            "allowed_domains": {"www.bloter.net", "bloter.net"},
        },
        "geeknews": {
            "homepage": "https://news.hada.io/",
            "rss": "https://feeds.feedburner.com/geeknews-feed",
            "seed_urls": [],
            "allowed_domains": {"news.hada.io"},
        },
        "newstap": {
            "homepage": "https://www.newstap.co.kr/",
            "rss": "https://cdn.newstap.co.kr/rss/gn_rss_allArticle.xml",
            "seed_urls": [],
            "allowed_domains": {"www.newstap.co.kr", "newstap.co.kr"},
        },
    }

    GENERAL_NON_ARTICLE_PATH_TOKENS = (
        "/rss",
        "/feed",
        "/feeds",
        "/index",
        "/tag/",
        "/tags/",
        "/topic/",
        "/topics/",
        "/section/",
        "/sections/",
        "/category/",
        "/categories/",
        "/archive",
        "/archives",
        "/author/",
        "/authors/",
        "/podcast",
        "/podcasts",
        "/newsletter",
        "/newsletters",
        "/video",
        "/videos",
        "/live",
        "/search",
        "/about",
        "/contact",
        "/newsroom",
    )

    def __init__(
        self,
        session: Optional[requests.Session] = None,
        config: Optional[dict] = None,
    ) -> None:
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": self.USER_AGENT})
        self.config = config or get_news_pipeline_config()
        self.processed_urls = set(get_processed_news_urls())

    def collect_ranked_articles(self) -> list[NewsArticle]:
        articles = []

        for source in self.config["sources"]:
            try:
                source_articles = self._collect_source_articles(source)
                articles.extend(source_articles)
            except Exception as exc:
                warning(f"Failed to collect from {source}: {exc}")

        deduped_articles = self._dedupe_articles(articles)
        ranked_articles = sorted(
            deduped_articles,
            key=lambda article: (article.score, article.published_at),
            reverse=True,
        )
        selected_articles = ranked_articles[: self.config["max_selected_articles"]]
        save_latest_news_candidates([asdict(article) for article in selected_articles])
        return selected_articles

    def _collect_source_articles(self, source: str) -> list[NewsArticle]:
        config = self.SOURCE_CONFIG[source]
        candidate_urls = []

        if config["rss"]:
            candidate_urls.extend(
                self._fetch_rss_urls(
                    config["rss"],
                    source,
                    config["allowed_domains"],
                )
            )

        listing_urls = config.get("seed_urls") or [config["homepage"]]
        for listing_url in listing_urls:
            candidate_urls.extend(
                self._extract_candidate_urls_from_homepage(
                    source,
                    listing_url,
                    config["allowed_domains"],
                )
            )

        unique_urls = []
        seen_urls = set()
        for url in candidate_urls:
            if url in seen_urls or url in self.processed_urls:
                continue
            seen_urls.add(url)
            unique_urls.append(url)

        articles = []
        for url in unique_urls[: self.config["max_candidates_per_source"] * 3]:
            article = self._fetch_article(source, url)
            if article is None:
                continue
            if not self._is_recent(article.published_at):
                continue
            articles.append(article)
            if len(articles) >= self.config["max_candidates_per_source"]:
                break

        info(f"Collected {len(articles)} news candidates from {source}.")
        return articles

    def _fetch_rss_urls(
        self,
        rss_url: str,
        source: str,
        allowed_domains: set[str],
    ) -> list[str]:
        response = self.session.get(rss_url, timeout=20)
        response.raise_for_status()

        root = ElementTree.fromstring(response.text)
        urls = []
        items = root.findall(".//item")
        if not items:
            items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
        for item in items:
            link = item.findtext("link", default="").strip()
            if not link:
                atom_link = item.find("{http://www.w3.org/2005/Atom}link")
                link = atom_link.attrib.get("href", "") if atom_link is not None else ""
            if link and self._is_valid_candidate_url(source, link, allowed_domains):
                urls.append(link)
        return urls

    def _extract_candidate_urls_from_homepage(
        self,
        source: str,
        homepage_url: str,
        allowed_domains: set[str],
    ) -> list[str]:
        response = self.session.get(homepage_url, timeout=20)
        response.raise_for_status()

        urls = []
        for href in self._extract_anchor_hrefs(response.text):
            absolute_url = urljoin(homepage_url, href.strip())
            if not self._is_valid_candidate_url(source, absolute_url, allowed_domains):
                continue
            urls.append(absolute_url)

        return urls

    def _is_valid_candidate_url(
        self,
        source: str,
        candidate_url: str,
        allowed_domains: set[str],
    ) -> bool:
        parsed = urlparse(candidate_url)
        if parsed.scheme not in {"http", "https"}:
            return False
        if parsed.netloc not in allowed_domains:
            return False

        path = parsed.path.lower()

        if path.endswith(".xml"):
            return False

        if any(token in path for token in self.GENERAL_NON_ARTICLE_PATH_TOKENS):
            return False

        if source == "theverge":
            return path.count("/") >= 2

        if source == "zdnet_korea":
            return path == "/view/" and "no=" in parsed.query

        if source == "bloter":
            return path.endswith("/articleview.html") and "idxno=" in parsed.query

        if source == "geeknews":
            return path == "/topic" and "id=" in parsed.query

        if source == "newstap":
            return path == "/news/articleview.html" and "idxno=" in parsed.query.lower()

        return False

    def _fetch_article(self, source: str, url: str) -> Optional[NewsArticle]:
        response = self.session.get(url, timeout=20)
        response.raise_for_status()
        document = response.text

        title = self._extract_title(document)
        published_at = self._extract_published_at(document, source)
        content = self._extract_content(document, source)
        summary = self._extract_summary(document, content)
        image_url = self._extract_image_url(document)
        category = self._extract_category(document, source)

        if not title or not content:
            return None

        if not self._looks_like_article(
            title=title,
            content=content,
            summary=summary,
            published_at=published_at,
        ):
            return None

        if not self._matches_device_focus(
            source=source,
            title=title,
            summary=summary,
            content=content,
            category=category,
        ):
            return None

        public_interest_score = self._score_public_interest(title, summary, content)
        realism_score = self._score_realism(title, summary, content)
        keyword_score = self._score_keyword_relevance(title, summary, content, source)
        llm_score, score_reason = self._score_with_llm(
            source=source,
            title=title,
            summary=summary,
            content=content,
            category=category,
            public_interest_score=public_interest_score,
            realism_score=realism_score,
        )
        score = self._calculate_final_score(
            public_interest_score=public_interest_score,
            realism_score=realism_score,
            llm_score=llm_score,
            keyword_score=keyword_score,
        )

        return NewsArticle(
            source=source,
            url=url,
            title=title,
            published_at=published_at,
            summary=summary,
            content=content,
            score=score,
            public_interest_score=public_interest_score,
            realism_score=realism_score,
            llm_score=llm_score,
            keyword_score=keyword_score,
            score_reason=score_reason,
            image_url=image_url,
            category=category,
        )

    def _looks_like_article(
        self,
        title: str,
        content: str,
        summary: str,
        published_at: str,
    ) -> bool:
        normalized_title = self._normalize_whitespace(title)
        normalized_summary = self._normalize_whitespace(summary)
        normalized_content = self._normalize_whitespace(content)

        if len(normalized_title) < 12:
            return False
        if len(normalized_summary) < 20:
            return False
        if self._count_words(normalized_content) < 45:
            return False
        if self._parse_datetime(published_at) is None:
            return False

        generic_titles = {
            "the verge",
            "zdnet korea",
            "bloter",
            "home",
            "latest news",
        }
        if normalized_title.lower() in generic_titles:
            return False

        return True

    def _matches_device_focus(
        self,
        source: str,
        title: str,
        summary: str,
        content: str,
        category: str,
    ) -> bool:
        full_text = f"{title}\n{summary}\n{content}".lower()
        title_text = title.lower()
        normalized_category = self._normalize_whitespace(category).lower()
        title_device_tokens = (
            "smartphone",
            "phone",
            "iphone",
            "galaxy",
            "laptop",
            "notebook",
            "tablet",
            "watch",
            "wearable",
            "earbuds",
            "headset",
            "camera",
            "display",
            "monitor",
            "tv",
            "battery",
            "gpu",
            "cpu",
            "chip",
            "semiconductor",
            "oled",
            "foldable",
            "스마트폰",
            "휴대폰",
            "아이폰",
            "갤럭시",
            "노트북",
            "태블릿",
            "워치",
            "웨어러블",
            "이어버드",
            "헤드셋",
            "카메라",
            "디스플레이",
            "모니터",
            "배터리",
            "gpu",
            "cpu",
            "칩",
            "반도체",
            "폴더블",
            "oled",
        )

        device_tokens = (
            "smartphone",
            "phone",
            "iphone",
            "galaxy",
            "laptop",
            "notebook",
            "tablet",
            "watch",
            "wearable",
            "earbuds",
            "headset",
            "xr",
            "vr",
            "ar",
            "camera",
            "display",
            "monitor",
            "tv",
            "battery",
            "gpu",
            "cpu",
            "chip",
            "semiconductor",
            "oled",
            "qd-oled",
            "foldable",
            "ai pc",
            "스마트폰",
            "휴대폰",
            "아이폰",
            "갤럭시",
            "노트북",
            "태블릿",
            "워치",
            "웨어러블",
            "이어버드",
            "헤드셋",
            "카메라",
            "디스플레이",
            "모니터",
            "tv",
            "배터리",
            "gpu",
            "cpu",
            "칩",
            "반도체",
            "폴더블",
            "oled",
            "qd-oled",
            "ai pc",
        )
        brand_tokens = (
            "apple",
            "samsung",
            "qualcomm",
            "mediatek",
            "intel",
            "amd",
            "nvidia",
            "sony",
            "lg",
            "xiaomi",
            "삼성",
            "애플",
            "퀄컴",
            "미디어텍",
            "인텔",
            "엔비디아",
            "소니",
            "샤오미",
            "lg",
        )
        launch_tokens = (
            "launch",
            "release",
            "unveil",
            "announce",
            "available",
            "shipping",
            "debut",
            "출시",
            "공개",
            "발표",
            "탑재",
            "양산",
            "상용",
        )
        business_tokens = (
            "earnings",
            "stock",
            "shareholder",
            "investor",
            "funding",
            "m&a",
            "acquisition",
            "merger",
            "ipo",
            "lawsuit",
            "ceo",
            "executive",
            "board",
            "strategy",
            "meeting",
            "실적",
            "주가",
            "주주",
            "투자자",
            "인수",
            "합병",
            "상장",
            "소송",
            "대표이사",
            "경영진",
            "이사회",
            "전략",
            "회동",
        )
        title_block_tokens = (
            "ceo",
            "executive",
            "earnings",
            "strategy",
            "meeting",
            "대표이사",
            "경영진",
            "실적",
            "회동",
            "주가",
            "투자자",
        )
        allowed_bloter_categories = {"it·과학", "미래산업"}

        device_hits = sum(token in full_text for token in device_tokens)
        brand_hits = sum(token in full_text for token in brand_tokens)
        launch_hits = sum(token in full_text for token in launch_tokens)
        business_hits = sum(token in full_text for token in business_tokens)

        positive_score = device_hits * 2 + brand_hits + launch_hits
        negative_score = business_hits * 2

        if source == "bloter":
            if normalized_category in allowed_bloter_categories:
                positive_score += 3
            elif normalized_category:
                negative_score += 3

        if device_hits >= 2:
            positive_score += 2

        if any(token in title_text for token in title_block_tokens):
            return False

        if not any(token in title_text for token in title_device_tokens):
            return False

        if device_hits == 0:
            return False

        return positive_score >= 4 and positive_score > negative_score

    def _extract_title(self, document: str) -> str:
        og_title = self._extract_meta_content(document, "og:title", "property")
        if og_title:
            return self._normalize_whitespace(og_title)

        h1 = self._extract_first_tag_text(document, "h1")
        if h1:
            return self._normalize_whitespace(h1)

        page_title = self._extract_first_tag_text(document, "title")
        page_title = re.sub(r"\s*[-|]\s*[^-|]+$", "", page_title).strip()
        return self._normalize_whitespace(page_title)

    def _extract_published_at(self, document: str, source: str) -> str:
        candidate_values = []
        time_datetime = self._extract_tag_attribute(document, "time", "datetime")
        time_text = self._extract_first_tag_text(document, "time")
        candidate_values.extend([time_datetime, time_text])

        for meta_name in (
            "article:published_time",
            "og:published_time",
            "parsely-pub-date",
        ):
            meta = self._extract_meta_content(document, meta_name, "property")
            if not meta:
                meta = self._extract_meta_content(document, meta_name, "name")
            if meta:
                candidate_values.append(meta)

        text_blob = self._html_to_text(document)
        if source == "zdnet_korea":
            match = re.search(r"입력\s*:\s*(\d{4}/\d{2}/\d{2}\s+\d{2}:\d{2})", text_blob)
            if match:
                candidate_values.append(match.group(1))

        for value in candidate_values:
            parsed_value = self._parse_datetime(value)
            if parsed_value is not None:
                return parsed_value.isoformat()

        return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    def _extract_content(self, document: str, source: str) -> str:
        selectors = []
        if source == "theverge":
            selectors = [
                ("tag", "article"),
                ("attr", "data-chorus-optimize-field", "body"),
            ]
        elif source == "zdnet_korea":
            selectors = [
                ("attr", "id", "articleBody"),
                ("attr", "class", "articleBody"),
                ("attr", "id", "article-body"),
            ]
        elif source == "bloter":
            selectors = [
                ("attr", "id", "article-view-content-div"),
                ("attr", "class", "article-view-content-div"),
                ("attr", "class", "entry-content"),
                ("tag", "article"),
            ]
        elif source == "newstap":
            selectors = [
                ("attr", "id", "article-view-content-div"),
                ("attr", "class", "article-body"),
                ("tag", "article"),
            ]

        paragraphs = []
        for selector in selectors:
            container = self._extract_container(document, selector)
            if not container:
                continue
            paragraphs = self._extract_paragraphs(container)
            if paragraphs:
                break

        if not paragraphs:
            paragraphs = self._extract_paragraphs(document)

        cleaned = []
        for paragraph in paragraphs:
            normalized = self._normalize_whitespace(paragraph)
            if len(normalized) < 40:
                continue
            if normalized.lower().startswith(("copyright", "관련기사", "connect with us")):
                continue
            cleaned.append(normalized)

        return "\n".join(cleaned[:12]).strip()

    def _extract_paragraphs(self, container_html: str) -> list[str]:
        paragraphs = [
            self._normalize_whitespace(self._strip_tags(match.group(1)))
            for match in re.finditer(
                r"<p\b[^>]*>(.*?)</p>",
                container_html,
                flags=re.IGNORECASE | re.DOTALL,
            )
        ]
        if paragraphs:
            return paragraphs
        text = self._html_to_text(container_html)
        return [chunk.strip() for chunk in text.split("\n") if chunk.strip()]

    def _extract_summary(self, document: str, content: str) -> str:
        for attr_name in ("description", "og:description", "twitter:description"):
            meta = self._extract_meta_content(document, attr_name, "name")
            if not meta:
                meta = self._extract_meta_content(document, attr_name, "property")
            if meta:
                return self._normalize_whitespace(meta)

        first_line = content.splitlines()[0] if content else ""
        return self._normalize_whitespace(first_line[:240])

    def _extract_image_url(self, document: str) -> str:
        for attr_name in ("og:image", "twitter:image"):
            meta = self._extract_meta_content(document, attr_name, "property")
            if not meta:
                meta = self._extract_meta_content(document, attr_name, "name")
            if meta:
                return meta.strip()
        return ""

    def _extract_category(self, document: str, source: str) -> str:
        if source == "zdnet_korea":
            match = re.search(
                r"([가-힣A-Za-z&/·]+)\s*입력\s*:",
                self._html_to_text(document),
            )
            if match:
                return self._normalize_whitespace(match.group(1))

        section = self._extract_meta_content(document, "article:section", "property")
        if section:
            return self._normalize_whitespace(section)

        return ""

    def _score_keyword_relevance(
        self,
        title: str,
        summary: str,
        content: str,
        source: str,
    ) -> int:
        full_text = f"{title}\n{summary}\n{content}".lower()
        score = 20
        korean_launch_tokens = ("출시", "공개", "발표", "탑재", "적용")
        korean_product_tokens = (
            "스마트폰",
            "노트북",
            "태블릿",
            "웨어러블",
            "카메라",
            "디스플레이",
            "배터리",
            "반도체",
            "제품",
            "기기",
        )
        korean_management_tokens = (
            "실적",
            "이사회",
            "인사",
            "전략",
            "투자자",
            "경영진",
            "대표이사",
        )

        launch_tokens = (
            "launch",
            "release",
            "unveil",
            "announce",
            "shipping",
            "available",
            "debut",
            "출시",
            "공개",
            "발표",
            "탑재",
            "적용",
        )
        product_tokens = (
            "smartphone",
            "phone",
            "laptop",
            "tablet",
            "watch",
            "wearable",
            "camera",
            "display",
            "battery",
            "chip",
            "consumer",
            "device",
            "product",
            "스마트폰",
            "노트북",
            "태블릿",
            "웨어러블",
            "카메라",
            "디스플레이",
            "배터리",
            "반도체",
            "제품",
        )
        management_tokens = (
            "ceo",
            "executive",
            "chairman",
            "board",
            "investor",
            "earnings",
            "strategy",
            "meeting",
            "transition",
            "appointment",
            "실적",
            "회동",
            "경영진",
            "인사",
            "전략",
            "투자자",
            "이사회",
            "대표이사",
        )

        for keyword in self.config["priority_keywords"]:
            if keyword.lower() in full_text:
                score += 3

        if any(token in full_text for token in launch_tokens):
            score += 12
        if any(token in full_text for token in korean_launch_tokens):
            score += 12

        if any(token in full_text for token in product_tokens):
            score += 10
        if any(token in full_text for token in korean_product_tokens):
            score += 10

        if any(
            token in full_text
            for token in (
                "battery",
                "display",
                "udc",
                "foldable",
                "semiconductor",
                "반도체",
                "디스플레이",
                "배터리",
            )
        ):
            score += 15
        if any(
            token in full_text
            for token in ("배터리", "디스플레이", "udc", "폴더블", "반도체")
        ):
            score += 15

        if any(token in full_text for token in management_tokens):
            score -= 12
        if any(token in full_text for token in korean_management_tokens):
            score -= 12

        if source in {"theverge", "zdnet_korea"}:
            score += 3

        return max(0, min(score, 100))

    def _score_public_interest(self, title: str, summary: str, content: str) -> int:
        full_text = f"{title}\n{summary}\n{content}".lower()
        score = 35
        korean_high_interest_tokens = (
            "모바일",
            "스마트폰",
            "노트북",
            "태블릿",
            "웨어러블",
            "배터리",
            "디스플레이",
            "카메라",
            "반도체",
        )
        korean_medium_interest_tokens = (
            "삼성",
            "애플",
            "소니",
            "샤오미",
            "퀄컴",
            "미디어텍",
            "엔비디아",
            "tsmc",
            "실리콘카본",
        )
        korean_far_from_consumer_tokens = (
            "적자",
            "실적",
            "인수",
            "규제",
            "정책",
            "주가",
            "재무",
        )
        korean_product_launch_tokens = ("출시", "공개", "발표", "탑재", "양산")
        korean_management_tokens = (
            "대표이사",
            "경영진",
            "이사회",
            "이동",
            "취임",
            "사임",
            "인사",
        )

        high_interest_tokens = (
            "smartphone",
            "phone",
            "iphone",
            "galaxy",
            "laptop",
            "tablet",
            "watch",
            "wearable",
            "display",
            "battery",
            "camera",
            "chip",
            "consumer",
            "모바일",
            "스마트폰",
            "노트북",
            "태블릿",
            "배터리",
            "디스플레이",
            "카메라",
            "반도체",
        )
        medium_interest_tokens = (
            "samsung",
            "apple",
            "sony",
            "xiaomi",
            "qualcomm",
            "mediatek",
            "nvidia",
            "tsmc",
            "foldable",
            "udc",
            "실리콘카본",
        )
        far_from_consumer_tokens = (
            "funding",
            "earnings",
            "lawsuit",
            "merger",
            "acquisition",
            "policy",
            "regulation",
            "stock",
            "finance",
            "투자",
            "실적",
            "인수",
            "합병",
            "규제",
            "정책",
        )
        product_launch_tokens = (
            "launch",
            "release",
            "shipping",
            "available",
            "consumer device",
            "new phone",
            "new laptop",
            "new tablet",
            "new watch",
            "출시",
            "공개",
            "발표",
            "탑재",
            "신제품",
        )
        management_tokens = (
            "ceo",
            "executive",
            "chairman",
            "board",
            "investor",
            "meeting",
            "transition",
            "appointment",
            "ceo transition",
            "대표이사",
            "경영진",
            "이사회",
            "회동",
            "취임",
            "사임",
            "인사",
        )

        for token in high_interest_tokens:
            if token in full_text:
                score += 8
        for token in korean_high_interest_tokens:
            if token in full_text:
                score += 8
        for token in medium_interest_tokens:
            if token in full_text:
                score += 4
        for token in korean_medium_interest_tokens:
            if token in full_text:
                score += 4
        for token in product_launch_tokens:
            if token in full_text:
                score += 6
        for token in korean_product_launch_tokens:
            if token in full_text:
                score += 6
        for token in far_from_consumer_tokens:
            if token in full_text:
                score -= 7
        for token in korean_far_from_consumer_tokens:
            if token in full_text:
                score -= 7
        for token in management_tokens:
            if token in full_text:
                score -= 8
        for token in korean_management_tokens:
            if token in full_text:
                score -= 8

        return max(0, min(score, 100))

    def _score_realism(self, title: str, summary: str, content: str) -> int:
        full_text = f"{title}\n{summary}\n{content}".lower()
        score = 45
        korean_near_term_tokens = (
            "출시",
            "양산",
            "상용",
            "적용",
            "탑재",
            "올해",
            "내년",
        )
        korean_far_term_tokens = ("언젠가", "장기", "미래형", "개념", "연구단계")
        korean_concrete_product_tokens = (
            "출시",
            "양산",
            "상용",
            "올해",
            "내년",
        )

        near_term_tokens = (
            "available",
            "shipping",
            "launch",
            "release",
            "this year",
            "next year",
            "production",
            "mass production",
            "commercial",
            "commercialization",
            "roadmap",
            "prototype",
            "debut",
            "출시",
            "양산",
            "상용화",
            "연내",
            "내년",
            "적용",
            "탑재",
        )
        far_term_tokens = (
            "someday",
            "decade",
            "2035",
            "2040",
            "research-only",
            "concept only",
            "moonshot",
            "long-term",
            "theoretical",
            "far future",
            "언젠가",
            "장기적",
            "미래형",
            "개념",
        )
        concrete_product_tokens = (
            "consumer product",
            "shipping",
            "available",
            "launch",
            "release",
            "this year",
            "next year",
            "mass production",
            "출시",
            "양산",
            "상용화",
            "연내",
            "내년",
        )

        for token in near_term_tokens:
            if token in full_text:
                score += 6
        for token in korean_near_term_tokens:
            if token in full_text:
                score += 6
        for token in concrete_product_tokens:
            if token in full_text:
                score += 5
        for token in korean_concrete_product_tokens:
            if token in full_text:
                score += 5
        for token in far_term_tokens:
            if token in full_text:
                score -= 10
        for token in korean_far_term_tokens:
            if token in full_text:
                score -= 10

        return max(0, min(score, 100))

    def _score_with_llm(
        self,
        source: str,
        title: str,
        summary: str,
        content: str,
        category: str,
        public_interest_score: int,
        realism_score: int,
    ) -> tuple[int, str]:
        if not self.config.get("use_llm_scoring", False):
            return 0, "LLM scoring disabled."

        model_name = get_default_text_model()
        if not model_name:
            return 0, "No default text model configured for LLM scoring."

        prompt = f"""
You are ranking tech news for a YouTube Shorts channel.

Evaluate the article on a 0-100 scale using these criteria:
1. Public interest: Is this about a mainstream product, feature, or technology ordinary consumers can understand or care about?
2. Realism: Is this likely to affect real consumer products or real-world usage within about 5 years?
3. Overall shorts-worthiness: Would this make a compelling short explainer today?

Return strict JSON only with this schema:
{{
  "score": <integer 0-100>,
  "reason": "<one short sentence>"
}}

Use the article itself as the main source of truth.
Do not invent facts.
Prefer lower scores for distant concept research, corporate finance news, lawsuits, and vague strategy updates.

Article:
Source: {source}
Category: {category}
Title: {title}
Summary: {summary}
Heuristic public interest score: {public_interest_score}
Heuristic realism score: {realism_score}
Content:
{content[:3000]}
""".strip()

        try:
            response = generate_text(prompt, model_name=model_name)
            cleaned = response.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(cleaned)
            score = int(parsed.get("score", 0))
            reason = self._normalize_whitespace(parsed.get("reason", ""))
            return max(0, min(score, 100)), reason
        except Exception as exc:
            return 0, f"LLM scoring failed: {exc}"

    def _calculate_final_score(
        self,
        public_interest_score: int,
        realism_score: int,
        llm_score: int,
        keyword_score: int,
    ) -> int:
        weights = self.config["scoring_weights"]
        final_score = (
            public_interest_score * weights["public_interest"]
            + realism_score * weights["realism"]
            + llm_score * weights["llm"]
            + keyword_score * weights["keyword"]
        )
        return max(0, min(int(round(final_score)), 100))

    def _dedupe_articles(self, articles: list[NewsArticle]) -> list[NewsArticle]:
        deduped = []
        seen_keys = set()

        for article in articles:
            key = self._build_dedupe_key(article)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(article)

        return deduped

    def _build_dedupe_key(self, article: NewsArticle) -> str:
        return re.sub(r"[^a-z0-9가-힣]+", " ", article.title.lower()).strip()

    def _is_recent(self, published_at: str) -> bool:
        parsed = self._parse_datetime(published_at)
        if parsed is None:
            return True

        cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            hours=self.config["max_article_age_hours"]
        )
        return parsed >= cutoff

    def _parse_datetime(self, raw_value: str) -> Optional[datetime]:
        value = str(raw_value).strip()
        if not value:
            return None

        normalized = value.replace("Z", "+00:00")
        for parser in (
            lambda item: datetime.fromisoformat(item),
            lambda item: datetime.strptime(item, "%Y/%m/%d %H:%M"),
            lambda item: datetime.strptime(item, "%Y-%m-%d %H:%M"),
            lambda item: parsedate_to_datetime(item),
        ):
            try:
                parsed = parser(normalized)
                if parsed.tzinfo is not None:
                    return parsed.astimezone().replace(tzinfo=None)
                return parsed
            except Exception:
                continue
        return None

    def _normalize_whitespace(self, value: str) -> str:
        return re.sub(r"\s+", " ", str(value)).strip()

    def _count_words(self, value: str) -> int:
        return len(re.findall(r"\S+", value))

    def _extract_anchor_hrefs(self, document: str) -> list[str]:
        return [
            html.unescape(match.group(1))
            for match in re.finditer(
                r"<a\b[^>]*href=['\"]([^'\"]+)['\"]",
                document,
                flags=re.IGNORECASE,
            )
        ]

    def _extract_meta_content(self, document: str, attr_value: str, attr_name: str) -> str:
        pattern = (
            r"<meta\b[^>]*"
            + attr_name
            + r"=['\"]"
            + re.escape(attr_value)
            + r"['\"][^>]*content=['\"]([^'\"]+)['\"][^>]*>"
        )
        match = re.search(pattern, document, flags=re.IGNORECASE)
        if match:
            return html.unescape(match.group(1))

        fallback_pattern = (
            r"<meta\b[^>]*content=['\"]([^'\"]+)['\"][^>]*"
            + attr_name
            + r"=['\"]"
            + re.escape(attr_value)
            + r"['\"][^>]*>"
        )
        match = re.search(fallback_pattern, document, flags=re.IGNORECASE)
        if match:
            return html.unescape(match.group(1))
        return ""

    def _extract_first_tag_text(self, document: str, tag_name: str) -> str:
        match = re.search(
            rf"<{tag_name}\b[^>]*>(.*?)</{tag_name}>",
            document,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return ""
        return self._normalize_whitespace(self._strip_tags(match.group(1)))

    def _extract_tag_attribute(self, document: str, tag_name: str, attribute: str) -> str:
        match = re.search(
            rf"<{tag_name}\b[^>]*\b{attribute}=['\"]([^'\"]+)['\"]",
            document,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if not match:
            return ""
        return html.unescape(match.group(1))

    def _extract_container(self, document: str, selector: tuple) -> str:
        if selector[0] == "tag":
            tag_name = selector[1]
            match = re.search(
                rf"<{tag_name}\b[^>]*>(.*?)</{tag_name}>",
                document,
                flags=re.IGNORECASE | re.DOTALL,
            )
            return match.group(1) if match else ""

        attr_name = selector[1]
        attr_value = selector[2]
        match = re.search(
            rf"<([a-z0-9]+)\b[^>]*\b{attr_name}=['\"][^'\"]*\b{re.escape(attr_value)}\b[^'\"]*['\"][^>]*>(.*?)</\1>",
            document,
            flags=re.IGNORECASE | re.DOTALL,
        )
        return match.group(2) if match else ""

    def _html_to_text(self, document: str) -> str:
        document = re.sub(
            r"<script\b[^>]*>.*?</script>",
            " ",
            document,
            flags=re.IGNORECASE | re.DOTALL,
        )
        document = re.sub(
            r"<style\b[^>]*>.*?</style>",
            " ",
            document,
            flags=re.IGNORECASE | re.DOTALL,
        )
        document = re.sub(r"</p\s*>", "\n", document, flags=re.IGNORECASE)
        document = re.sub(r"<br\s*/?>", "\n", document, flags=re.IGNORECASE)
        return self._normalize_whitespace(self._strip_tags(document).replace("\xa0", " "))

    def _strip_tags(self, document: str) -> str:
        return html.unescape(re.sub(r"<[^>]+>", " ", document))


def article_to_prompt_context(article: NewsArticle) -> str:
    content = article.content
    if len(content) > 1200:
        content = content[:1200].rstrip() + "..."
    date_to_mention = article.published_at[:10]
    natural_date = date_to_mention
    if len(date_to_mention) == 10 and date_to_mention[4] == "-" and date_to_mention[7] == "-":
        year, month, day = date_to_mention.split("-")
        natural_date = f"{year}년 {int(month)}월 {int(day)}일"

    return (
        f"Source: {article.source}\n"
        f"URL: {article.url}\n"
        f"Published At: {article.published_at}\n"
        f"Article Date To Mention: {article.published_at[:10]}\n"
        f"Natural Korean Article Date: {natural_date}\n"
        f"Title: {article.title}\n"
        f"Summary: {article.summary}\n"
        f"Public Interest Score: {article.public_interest_score}\n"
        f"Realism Score: {article.realism_score}\n"
        f"LLM Score: {article.llm_score}\n"
        f"Keyword Score: {article.keyword_score}\n"
        f"Final Score: {article.score}\n"
        f"Score Reason: {article.score_reason}\n"
        f"Content:\n{content}\n"
    )


def dump_ranked_articles_json(articles: list[NewsArticle]) -> str:
    return json.dumps([asdict(article) for article in articles], indent=2, ensure_ascii=False)
