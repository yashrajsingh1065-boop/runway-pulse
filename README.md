# Runway Pulse

**Menswear runway intelligence from public show coverage — scraped, vision-tagged, and readable in one dashboard.**

Every season, thousands of runway looks are published openly. Anyone deciding
what to design, buy or stock next year needs to know what just walked: which
colours dominated, which silhouettes are rising, how this season compares to
last. The trend services that answer those questions start at several thousand
dollars a seat — so most of the industry answers them by scrolling.

Runway Pulse turns public runway coverage into structured data:

```
scrape shows ─> download looks ─> vision-tag each look ─> aggregate ─> dashboard
                                   (garment categories,
                                    colours, fabrics,
                                    tailoring details)
```

## What it extracts

- **Garment detection** — each look is segmented and tagged against the
  [Fashionpedia](https://fashionpedia.github.io/home/) ontology: categories,
  silhouettes, necklines, closures.
- **Colour analysis** — dominant colours per look, clustered into families, so
  a season's palette is a chart rather than an impression.
- **Tailoring detail** — an LLM pass over suit and blazer looks extracts lapel
  style, button stance, fit and fabric texture into queryable fields.
- **Mood clustering** — looks grouped into archetypes, so "what stories did
  this season tell" has a quantitative answer.

## Dashboard

A Streamlit app with four views: an overview with per-show stats and filters
across every extracted attribute; trend timelines across seasons;
season-vs-season comparison; and colour-family evolution.

```bash
python -m streamlit run dashboard/app.py
```

## Pipeline

```bash
pip install -r requirements.txt
cp .env.example .env          # add your Anthropic API key for the tailoring pass

python main.py scrape         # index shows and looks
python main.py download       # fetch look images (rate-limited, resumable)
python main.py analyze        # vision + colour + tailoring extraction
```

Everything lands in a local SQLite database. The scraper is polite: rate
limits, resumable batches, and no attempt to defeat anything.

## What is deliberately not here

The repository ships **code only** — no scraped images and no database. Runway
photography is editorial content that belongs to its publishers; this tool
analyses it locally the way a person with a browser would, and republishing the
underlying photographs is not part of that. Run the pipeline yourself and the
data is yours to look at.

## Stack

Python · Scrapy · Fashionpedia vision models · Anthropic batch API for the
tailoring pass · SQLite · Streamlit

## Licence

MIT.
