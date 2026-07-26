from __future__ import annotations

import json
import logging
import re

import scrapy
from scrapy.crawler import CrawlerProcess

from config import VOGUE_BASE_URL, VOGUE_SEASON_URL, SEASON_PERIODS
from storage.database import (
    get_or_create_show,
    save_look,
    update_show_look_count,
    get_season_by_code,
    get_fashion_week_by_key,
)
from ingestion.image_store import ImageStore

logger = logging.getLogger(__name__)


def _extract_preloaded_state(response) -> dict | None:
    """Extract window.__PRELOADED_STATE__ JSON from script tags."""
    for script in response.css("script::text").getall():
        match = re.search(r"window\.__PRELOADED_STATE__\s*=\s*(\{.+\})", script, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                logger.warning("Failed to parse __PRELOADED_STATE__ JSON")
                continue
    return None


class VogueRunwaySpider(scrapy.Spider):
    name = "vogue_runway"
    allowed_domains = ["vogue.com"]

    def __init__(self, season_code: str, week_key: str, download_images: bool = True, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.season_code = season_code
        self.week_key = week_key
        self.download_images = download_images

        # Parse season code (e.g. "FW25" -> period="fall", year=2025)
        prefix = season_code[:2]
        year_short = season_code[2:]
        self.year = 2000 + int(year_short)
        self.period = SEASON_PERIODS[prefix]["period"]

        # Resolve DB references
        self.season = get_season_by_code(season_code)
        self.fashion_week = get_fashion_week_by_key(week_key)

        if not self.season:
            raise ValueError(f"Season '{season_code}' not found in database. Run 'db init' first.")

        self.image_store = ImageStore() if download_images else None

    def start_requests(self):
        url = VOGUE_SEASON_URL.format(period=self.period, year=self.year)
        yield scrapy.Request(url, callback=self.parse_season)

    def parse_season(self, response):
        """Extract designer show links from the season listing page."""
        state = _extract_preloaded_state(response)

        if state:
            yield from self._parse_season_from_json(state, response)
        else:
            yield from self._parse_season_from_html(response)

    def _parse_season_from_json(self, state, response):
        """Parse designer listings from transformed.runwaySeasonContent."""
        try:
            rsc = state.get("transformed", {}).get("runwaySeasonContent", {})
            all_shows = rsc.get("allShows", [])

            count = 0
            for group in all_shows:
                for link in group.get("links", []):
                    url = link.get("url", "")
                    text = link.get("text", "")
                    if url:
                        slug = url.rstrip("/").split("/")[-1]
                        yield scrapy.Request(
                            response.urljoin(url),
                            callback=self.parse_show,
                            meta={"designer_slug": slug, "designer_name": text or slug.replace("-", " ").title()},
                        )
                        count += 1

            logger.info("Found %d shows from JSON on %s", count, response.url)

            if count == 0:
                logger.warning("No shows in runwaySeasonContent, falling back to HTML")
                yield from self._parse_season_from_html(response)

        except (KeyError, TypeError) as exc:
            logger.warning("JSON structure unexpected: %s. Falling back to HTML.", exc)
            yield from self._parse_season_from_html(response)

    def _parse_season_from_html(self, response):
        """Fallback: parse show links from HTML."""
        links = response.css('a[href*="/fashion-shows/"]::attr(href)').getall()
        season_slug = f"{self.period}-{self.year}-menswear"
        seen = set()
        for href in links:
            if season_slug in href and href.count("/") >= 4:
                full_url = response.urljoin(href)
                if full_url not in seen:
                    seen.add(full_url)
                    slug = href.rstrip("/").split("/")[-1]
                    yield scrapy.Request(
                        full_url,
                        callback=self.parse_show,
                        meta={"designer_slug": slug, "designer_name": slug.replace("-", " ").title()},
                    )
        logger.info("Found %d show links from HTML on %s", len(seen), response.url)

    def parse_show(self, response):
        """Extract look images from a show gallery page."""
        designer_slug = response.meta["designer_slug"]
        designer_name = response.meta["designer_name"]

        state = _extract_preloaded_state(response)
        image_urls = []

        if state:
            image_urls = self._extract_images_from_json(state)

        if not image_urls:
            image_urls = self._extract_images_from_html(response)

        if not image_urls:
            logger.warning("No images found for %s at %s", designer_name, response.url)
            return

        # Save show to DB
        show_id = get_or_create_show(
            season_id=self.season["id"],
            fashion_week_id=self.fashion_week["id"] if self.fashion_week else None,
            designer=designer_name,
            designer_slug=designer_slug,
            source_url=response.url,
        )

        # Save looks
        look_items = []
        for i, img_url in enumerate(image_urls, start=1):
            look_id = save_look(show_id, i, img_url)
            if look_id:
                look_items.append({
                    "look_id": look_id,
                    "look_number": i,
                    "image_url": img_url,
                })

        update_show_look_count(show_id, len(image_urls))

        logger.info(
            "%s: %d looks (%d new)",
            designer_name, len(image_urls), len(look_items),
        )

        # Download images if enabled
        if self.image_store and look_items:
            stats = self.image_store.download_batch(
                look_items, self.season_code, designer_slug
            )
            logger.info(
                "%s images: %d downloaded, %d skipped, %d failed",
                designer_name, stats["downloaded"], stats["skipped"], stats["failed"],
            )

        yield {
            "designer": designer_name,
            "designer_slug": designer_slug,
            "show_id": show_id,
            "total_looks": len(image_urls),
            "new_looks": len(look_items),
        }

    def _extract_images_from_json(self, state: dict) -> list[str]:
        """Pull look image URLs from transformed.runwayShowGalleries.collectionSlides."""
        urls = []
        try:
            t = state.get("transformed", {})
            galleries = t.get("runwayShowGalleries", {})
            slides = galleries.get("collectionSlides", [])

            for slide in slides:
                if not isinstance(slide, dict):
                    continue
                image = slide.get("image", {})
                if isinstance(image, dict):
                    sources = image.get("sources", {})
                    # Prefer largest available rendition
                    for size in ("xl", "lg", "md", "sm"):
                        src = sources.get(size, {})
                        if isinstance(src, dict) and src.get("url"):
                            urls.append(src["url"])
                            break
                    else:
                        # Try direct url on image
                        if image.get("url"):
                            urls.append(image["url"])

            if urls:
                return urls

            # Fallback: try galleries[].items[]
            for gallery in galleries.get("galleries", []):
                for item in gallery.get("items", []):
                    if isinstance(item, dict):
                        image = item.get("image", {})
                        if isinstance(image, dict):
                            sources = image.get("sources", {})
                            for size in ("xl", "lg", "md", "sm"):
                                src = sources.get(size, {})
                                if isinstance(src, dict) and src.get("url"):
                                    urls.append(src["url"])
                                    break

        except (KeyError, TypeError, AttributeError) as exc:
            logger.debug("JSON image extraction failed: %s", exc)

        return urls

    def _extract_images_from_html(self, response) -> list[str]:
        """Fallback: extract runway images from HTML img tags."""
        urls = []
        for img in response.css("img"):
            src = img.attrib.get("src", "") or img.attrib.get("data-src", "")
            if src and any(hint in src.lower() for hint in ("runway", "look", "collection", "credit-gorunway")):
                urls.append(response.urljoin(src))
        seen = set()
        unique = []
        for url in urls:
            if url not in seen:
                seen.add(url)
                unique.append(url)
        return unique


def run_spider(season_code: str, week_key: str, download_images: bool = True) -> None:
    """Run the Vogue runway spider."""
    from ingestion.scrapy_settings import get_settings

    process = CrawlerProcess(get_settings())
    process.crawl(
        VogueRunwaySpider,
        season_code=season_code,
        week_key=week_key,
        download_images=download_images,
    )
    process.start()
