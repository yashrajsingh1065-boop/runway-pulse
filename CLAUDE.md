# CLAUDE.md

## Commands

```bash
# Setup
cd /Users/yashrajsingh/runway-pulse
python3 -m venv .venv && source .venv/bin/activate && pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env  # add ANTHROPIC_API_KEY

# Database
python main.py db init    # create tables + seed data
python main.py db stats   # show counts

# Scraping
python main.py scrape runway --season FW25 --week paris              # scrape + download images
python main.py scrape runway --season FW25 --week paris --no-images  # scrape metadata only

# Dashboard
python main.py dashboard  # Streamlit on :8501
```

## Architecture

Runway Pulse is a menswear trend analysis tool. It scrapes runway show images, analyzes them with computer vision and Claude AI, and surfaces trend data via a Streamlit dashboard.

### Pipeline Flow (planned phases)

```
Phase 1: Vogue Runway scraping → image download → SQLite storage → Streamlit dashboard
Phase 2: CV garment detection → color extraction → silhouette classification
Phase 3: Claude AI look analysis → styling notes → designer intent
Phase 4: Trend aggregation → season-over-season comparison → direction scoring
Phase 5: Street style ingestion → adoption metrics → runway-to-street lag
Phase 6: Reports → Notion integration → fashion news monitoring
```

### Module Responsibilities

- **`config.py`** — Paths, env vars, fashion weeks dict, season periods, Vogue URL patterns, scraper/CV settings
- **`storage/database.py`** — SQLite WAL mode, 12 tables, seed data (fashion weeks + seasons), Phase 1 CRUD operations
- **`ingestion/runway_scraper.py`** — Scrapy spider parsing Vogue's `__PRELOADED_STATE__` JSON for show/look data
- **`ingestion/scrapy_settings.py`** — Scrapy configuration (delays, concurrency, robots.txt)
- **`ingestion/image_store.py`** — ThreadPoolExecutor image downloader with SHA256 dedup
- **`cli/commands.py`** — Click CLI: scrape, db, dashboard command groups
- **`dashboard/app.py`** — Streamlit dashboard: metrics, charts, image grid browser

### Database Schema (12 tables)

- **Reference:** fashion_weeks, seasons (seeded on init)
- **Core:** shows, looks
- **CV output (Phase 2-3):** garment_attributes, look_analysis
- **Trends (Phase 4):** trend_snapshots
- **Street style (Phase 5):** street_images, street_garment_attributes
- **Adoption (Phase 5-6):** adoption_metrics, reports, fashion_news

### Key Configuration

- `FASHION_WEEKS` — 10 fashion weeks (Paris, Milan, London, NY, Florence, Tokyo, Seoul, Copenhagen, Shanghai, Mumbai)
- `SEASON_PERIODS` — FW (Fall/Winter), SS (Spring/Summer)
- Scraper: DOWNLOAD_DELAY=2, CONCURRENT=4, ROBOTSTXT_OBEY=True
- Image download: 6 workers, SHA256 dedup, organized by season/designer/look

### Environment Variables

- `ANTHROPIC_API_KEY` — required for Claude analysis (Phase 3+)
- `LOG_LEVEL` — defaults to INFO
- `DASHBOARD_PORT` — defaults to 8501
