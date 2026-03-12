from config import (
    SCRAPER_DOWNLOAD_DELAY,
    SCRAPER_CONCURRENT,
    SCRAPER_ROBOTSTXT_OBEY,
    SCRAPER_USER_AGENT,
)


def get_settings() -> dict:
    """Return Scrapy settings dict."""
    return {
        "BOT_NAME": "runway_pulse",
        "SPIDER_MODULES": ["ingestion"],
        "NEWSPIDER_MODULE": "ingestion",
        "USER_AGENT": SCRAPER_USER_AGENT,
        "ROBOTSTXT_OBEY": SCRAPER_ROBOTSTXT_OBEY,
        "DOWNLOAD_DELAY": SCRAPER_DOWNLOAD_DELAY,
        "CONCURRENT_REQUESTS": SCRAPER_CONCURRENT,
        "CONCURRENT_REQUESTS_PER_DOMAIN": SCRAPER_CONCURRENT,
        "COOKIES_ENABLED": False,
        "TELNETCONSOLE_ENABLED": False,
        "LOG_LEVEL": "INFO",
        "REQUEST_FINGERPRINTER_IMPLEMENTATION": "2.7",
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
        "FEED_EXPORT_ENCODING": "utf-8",
    }
