PHASE_1_SOURCES = [
    {
        "id": "the_verge",
        "name": "The Verge",
        "tier": "news_secondary",
        "rss_url": "https://www.theverge.com/rss/index.xml",
    },
    {
        "id": "gsmarena",
        "name": "GSMArena",
        "tier": "news_secondary",
        "rss_url": "https://www.gsmarena.com/rss-news-reviews.php3",
    },
    {
        "id": "android_authority",
        "name": "Android Authority",
        "tier": "news_secondary",
        "rss_url": "https://www.androidauthority.com/feed/",
    },
    {
        "id": "9to5mac",
        "name": "9to5Mac",
        "tier": "news_secondary",
        "rss_url": "https://9to5mac.com/feed/",
    },
    {
        "id": "zdnet_korea",
        "name": "ZDNet Korea",
        "tier": "news_secondary",
        "rss_url": "https://feeds.feedburner.com/zdkorea",
    },
    {
        "id": "bloter",
        "name": "Bloter",
        "tier": "news_secondary",
        "rss_url": "https://cdn.bloter.net/rss/gns_allArticle.xml",
    },
    {
        "id": "underkg",
        "name": "UNDERkg",
        "tier": "news_secondary",
        "rss_url": "https://underkg.co.kr:44391/rss",
    },
    {
        "id": "geeknews",
        "name": "GeekNews",
        "tier": "tech_secondary",
        "rss_url": "https://feeds.feedburner.com/geeknews-feed",
    },
    {
        "id": "newstap",
        "name": "NewsTap",
        "tier": "news_secondary",
        "rss_url": "https://cdn.newstap.co.kr/rss/gn_rss_allArticle.xml",
    },
    {
        "id": "google_news_query_launches_ko",
        "name": "Google News KR Launch Query",
        "tier": "search_aggregator",
        "rss_url": "https://news.google.com/rss/search?q=(%EC%82%BC%EC%84%B1%20OR%20%EC%95%A0%ED%94%8C%20OR%20%ED%80%84%EC%BB%B4%20OR%20%EC%83%A4%EC%98%A4%EB%AF%B8%20OR%20%EB%82%AB%EC%8B%B1%20OR%20NVIDIA%20OR%20AMD%20OR%20Intel%20OR%20CPU%20OR%20GPU%20OR%20PC%20OR%20%EB%85%B8%ED%8A%B8%EB%B6%81%20OR%20%ED%82%A4%EB%B3%B4%EB%93%9C%20OR%20%EB%A7%88%EC%9A%B0%EC%8A%A4%20OR%20%ED%97%A4%EB%93%9C%EC%85%8B%20OR%20%EC%9D%B4%EC%96%B4%ED%8F%B0%20OR%20%EC%8A%A4%EB%A7%88%ED%8A%B8%EC%9B%8C%EC%B9%98%20OR%20%EC%8A%A4%EB%A7%88%ED%8A%B8%EB%B0%B4%EB%93%9C%20OR%20%EC%9B%A8%EC%96%B4%EB%9F%AC%EB%B8%94%20OR%20headset%20OR%20earbuds%20OR%20smartwatch%20OR%20wearable)%20(%EC%B6%9C%EC%8B%9C%20OR%20%EA%B3%B5%EA%B0%9C%20OR%20%EB%B0%9C%ED%91%9C)&hl=ko&gl=KR&ceid=KR:ko",
    },
]


# Dedicated feeds for the 13:00 product-launch/new-release slot. Keep these
# separate from the general pool so the scheduled product job does not depend on
# broad tech feeds that often classify as component/market news.
PRODUCT_LAUNCH_SOURCES = [
    {
        "id": "google_news_product_launch_ko",
        "name": "Google News KR Product Launch Query",
        "tier": "search_aggregator",
        "rss_url": "https://news.google.com/rss/search?q=(%EC%82%BC%EC%84%B1%20OR%20%EA%B0%A4%EB%9F%AD%EC%8B%9C%20OR%20%EC%95%A0%ED%94%8C%20OR%20%EC%95%84%EC%9D%B4%ED%8F%B0%20OR%20%EC%95%84%EC%9D%B4%ED%8C%A8%EB%93%9C%20OR%20%EB%A7%A5%EB%B6%81%20OR%20%EC%83%A4%EC%98%A4%EB%AF%B8%20OR%20%EB%A0%88%EB%85%B8%EB%B2%84%20OR%20ASUS%20OR%20ROG%20OR%20%EB%A1%9C%EC%A7%80%ED%85%8D%20OR%20%EC%86%8C%EB%8B%88%20OR%20%EB%82%AB%EC%8B%B1%20OR%20%EC%9D%B8%ED%85%94%20OR%20AMD%20OR%20NVIDIA)%20(%EC%8B%A0%EC%A0%9C%ED%92%88%20OR%20%EC%B6%9C%EC%8B%9C%20OR%20%EA%B3%B5%EA%B0%9C%20OR%20%EB%B0%9C%ED%91%9C%20OR%20%EC%82%AC%EC%A0%84%EC%98%88%EC%95%BD%20OR%20%EA%B5%AD%EB%82%B4%20%EC%B6%9C%EC%8B%9C)&hl=ko&gl=KR&ceid=KR:ko",
    },
    {
        "id": "google_news_product_launch_en",
        "name": "Google News Global Product Launch Query",
        "tier": "search_aggregator",
        "rss_url": "https://news.google.com/rss/search?q=(Samsung%20OR%20Galaxy%20OR%20Apple%20OR%20iPhone%20OR%20iPad%20OR%20MacBook%20OR%20Xiaomi%20OR%20Nothing%20OR%20Lenovo%20OR%20ASUS%20OR%20ROG%20OR%20Logitech%20OR%20Sony%20OR%20Intel%20OR%20AMD%20OR%20NVIDIA)%20(new%20product%20OR%20launch%20OR%20launches%20OR%20launched%20OR%20unveils%20OR%20announces%20OR%20release%20OR%20preorder)&hl=ko&gl=KR&ceid=KR:ko",
    },
    {
        "id": "google_news_device_availability_ko",
        "name": "Google News KR Device Availability Query",
        "tier": "search_aggregator",
        "rss_url": "https://news.google.com/rss/search?q=(%EC%8A%A4%EB%A7%88%ED%8A%B8%ED%8F%B0%20OR%20%EB%85%B8%ED%8A%B8%EB%B6%81%20OR%20PC%20OR%20%EA%B2%8C%EC%9D%B4%EB%B0%8D%20OR%20%ED%82%A4%EB%B3%B4%EB%93%9C%20OR%20%EB%A7%88%EC%9A%B0%EC%8A%A4%20OR%20%ED%97%A4%EB%93%9C%EC%85%8B%20OR%20%EC%9D%B4%EC%96%B4%ED%8F%B0%20OR%20%EC%8A%A4%EB%A7%88%ED%8A%B8%EC%9B%8C%EC%B9%98)%20(%EA%B5%AD%EB%82%B4%20%EC%B6%9C%EC%8B%9C%20OR%20%ED%8C%90%EB%A7%A4%20%EC%8B%9C%EC%9E%91%20OR%20%EC%98%88%EC%95%BD%20%ED%8C%90%EB%A7%A4%20OR%20%EC%82%AC%EC%A0%84%EC%98%88%EC%95%BD)&hl=ko&gl=KR&ceid=KR:ko",
    },
    {
        "id": "newstap_product_launch",
        "name": "NewsTap Product News",
        "tier": "news_secondary",
        "rss_url": "https://www.newstap.co.kr/rss/S1N2.xml",
    },
]
