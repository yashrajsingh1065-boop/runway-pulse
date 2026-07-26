from __future__ import annotations

import sys
import logging

import click
from rich.console import Console
from rich.table import Table

from config import FASHION_WEEKS, DASHBOARD_PORT, LOG_LEVEL, CV_DEVICE

console = Console()
logger = logging.getLogger(__name__)


@click.group()
def cli():
    """Runway Pulse — Menswear trend analysis tool."""
    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


# ── Database commands ─────────────────────────────────────────────────────────


@cli.group()
def db():
    """Database management commands."""
    pass


@db.command("init")
def db_init():
    """Initialize the database with all tables and seed data."""
    from storage.database import init_db
    init_db()
    console.print("[bold green]Database initialized.[/bold green]")

    from storage.database import get_show_stats
    stats = get_show_stats()
    console.print(f"  Fashion weeks: {stats['fashion_weeks']}")
    console.print(f"  Seasons: {stats['seasons']}")
    console.print(f"  Shows: {stats['shows']}")
    console.print(f"  Looks: {stats['looks']}")
    console.print(f"  Images: {stats['images']}")


@db.command("stats")
def db_stats():
    """Show database statistics."""
    from storage.database import get_show_stats, get_recent_shows, get_looks_per_season

    stats = get_show_stats()

    table = Table(title="Runway Pulse Stats")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", style="green", justify="right")
    table.add_row("Fashion Weeks", str(stats["fashion_weeks"]))
    table.add_row("Seasons", str(stats["seasons"]))
    table.add_row("Shows", str(stats["shows"]))
    table.add_row("Looks", str(stats["looks"]))
    table.add_row("Downloaded Images", str(stats["images"]))
    console.print(table)

    season_data = get_looks_per_season()
    if season_data:
        console.print()
        st = Table(title="Looks per Season")
        st.add_column("Season", style="cyan")
        st.add_column("Looks", style="green", justify="right")
        for row in season_data:
            st.add_row(row["season_code"], str(row["look_count"]))
        console.print(st)

    recent = get_recent_shows(10)
    if recent:
        console.print()
        rt = Table(title="Recent Shows")
        rt.add_column("Designer", style="cyan")
        rt.add_column("Season", style="yellow")
        rt.add_column("Week", style="magenta")
        rt.add_column("Looks", style="green", justify="right")
        for show in recent:
            rt.add_row(
                show["designer"],
                show["season_code"] or "—",
                show["fashion_week_name"] or "—",
                str(show["look_count"] or 0),
            )
        console.print(rt)


# ── Scrape commands ───────────────────────────────────────────────────────────


@cli.group()
def scrape():
    """Scraping commands."""
    pass


@scrape.command("runway")
@click.option("--season", required=True, help="Season code, e.g. FW25, SS26")
@click.option("--week", required=True, type=click.Choice(list(FASHION_WEEKS.keys())), help="Fashion week key")
@click.option("--no-images", is_flag=True, help="Skip image downloads")
def scrape_runway(season, week, no_images):
    """Scrape runway shows from Vogue."""
    from storage.database import get_season_by_code
    s = get_season_by_code(season)
    if not s:
        console.print(f"[red]Season '{season}' not found. Run 'db init' first.[/red]")
        sys.exit(1)

    fw = FASHION_WEEKS[week]
    console.print(f"Scraping [bold]{fw['name']}[/bold] — [cyan]{season}[/cyan]")
    if no_images:
        console.print("[yellow]Image downloads disabled.[/yellow]")

    from ingestion.runway_scraper import run_spider
    run_spider(season_code=season, week_key=week, download_images=not no_images)

    console.print("[bold green]Scrape complete.[/bold green]")


# ── Dashboard command ─────────────────────────────────────────────────────────


# ── Vision commands ──────────────────────────────────────────────────────────


@cli.group()
def vision():
    """Computer vision detection commands."""
    pass


@vision.command("process")
@click.option("--season", default=None, help="Season code, e.g. FW25, SS26")
@click.option("--show-id", default=None, type=int, help="Process a single show by ID")
@click.option("--device", default=None, type=click.Choice(["auto", "mps", "cpu"]), help="Override CV device")
def vision_process(season, show_id, device):
    """Run garment detection on runway images."""
    if not season and not show_id:
        console.print("[red]Provide --season or --show-id[/red]")
        raise SystemExit(1)

    # Run migration first
    from storage.database import migrate_phase2
    migrate_phase2()

    # Override device if requested
    if device:
        import config
        config.CV_DEVICE = device

    from vision.detector import process_season, process_show

    if show_id:
        stats = process_show(show_id)
    else:
        stats = process_season(season)

    console.print()
    console.print(f"[bold green]Done![/bold green] Processed {stats['processed']} looks")
    console.print(f"  Detections: {stats['detections']}")
    console.print(f"  Suits: {stats['suit']}")
    console.print(f"  Blazers: {stats['blazer']}")
    console.print(f"  Overcoats: {stats['overcoat']}")


@vision.command("stats")
def vision_stats():
    """Show garment detection statistics."""
    from storage.database import get_detection_stats
    stats = get_detection_stats()

    table = Table(title="CV Detection Stats")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", style="green", justify="right")
    table.add_row("CV Processed Looks", f"{stats['cv_processed']}/{stats['total_looks']}")
    table.add_row("Total Detections", str(stats["total_detections"]))
    console.print(table)

    if stats["garment_types"]:
        console.print()
        gt = Table(title="Garment Types Detected")
        gt.add_column("Type", style="cyan")
        gt.add_column("Count", style="green", justify="right")
        for gtype, count in stats["garment_types"].items():
            gt.add_row(gtype, str(count))
        console.print(gt)

    if stats["categories"]:
        console.print()
        ct = Table(title="Look Categories")
        ct.add_column("Category", style="cyan")
        ct.add_column("Looks", style="green", justify="right")
        for cat, count in stats["categories"].items():
            ct.add_row(cat, str(count))
        console.print(ct)


# ── Analyze commands ─────────────────────────────────────────────────────────


@cli.group()
def analyze():
    """Claude AI analysis commands."""
    pass


@analyze.command("suits")
@click.option("--season", required=True, help="Season code, e.g. FW25")
def analyze_suits(season):
    """Submit suit/blazer looks for Claude Batch API analysis."""
    from ai.suit_analyzer import submit_batch

    console.print(f"Submitting batch for [cyan]{season}[/cyan] suit/blazer looks...")
    batch_id = submit_batch(season)

    if not batch_id:
        console.print("[yellow]No suit/blazer looks to analyze.[/yellow]")
        return

    console.print(f"[bold green]Batch submitted![/bold green] ID: [cyan]{batch_id}[/cyan]")
    console.print("Run [bold]python main.py analyze status[/bold] to check progress.")


@analyze.command("status")
@click.option("--batch-id", default=None, help="Specific batch ID to check")
def analyze_status(batch_id):
    """Check Claude batch analysis status."""
    from ai.suit_analyzer import check_batch_status, list_batches

    if batch_id:
        status = check_batch_status(batch_id)
        console.print(f"Batch [cyan]{status['id']}[/cyan]: {status['processing_status']}")
        rc = status["request_counts"]
        console.print(f"  Processing: {rc['processing']}  Succeeded: {rc['succeeded']}  Errored: {rc['errored']}")
    else:
        batches = list_batches()
        if not batches:
            console.print("[yellow]No batches found.[/yellow]")
            return
        bt = Table(title="Recent Batches")
        bt.add_column("ID", style="cyan")
        bt.add_column("Status", style="yellow")
        bt.add_column("Succeeded", style="green", justify="right")
        bt.add_column("Errored", style="red", justify="right")
        bt.add_column("Processing", style="blue", justify="right")
        for b in batches:
            rc = b["request_counts"]
            bt.add_row(b["id"], b["processing_status"], str(rc["succeeded"]), str(rc["errored"]), str(rc["processing"]))
        console.print(bt)


@analyze.command("fetch")
@click.option("--batch-id", required=True, help="Batch ID to fetch results from")
def analyze_fetch(batch_id):
    """Fetch and save Claude batch analysis results."""
    from ai.suit_analyzer import fetch_batch_results

    console.print(f"Fetching results for batch [cyan]{batch_id}[/cyan]...")
    result = fetch_batch_results(batch_id)

    if result["status"] != "ended":
        console.print(f"[yellow]Batch not complete yet. Status: {result['status']}[/yellow]")
        return

    console.print(f"[bold green]Results saved![/bold green]")
    console.print(f"  Saved: {result['saved']}")
    console.print(f"  Errors: {result['errors']}")


# ── Trend commands ────────────────────────────────────────────────────────────


@cli.group()
def trends():
    """Trend aggregation and comparison commands."""
    pass


@trends.command("aggregate")
@click.option("--season", required=True, help="Season code, e.g. FW25")
@click.option("--compare-to", default=None, help="Previous season to compare against, e.g. FW25")
def trends_aggregate(season, compare_to):
    """Aggregate trend attributes for a season."""
    from storage.database import get_season_by_code
    s = get_season_by_code(season)
    if not s:
        console.print(f"[red]Season '{season}' not found.[/red]")
        raise SystemExit(1)

    from analysis.trend_engine import aggregate_season, compare_seasons

    console.print(f"Aggregating trends for [cyan]{season}[/cyan]...")
    count = aggregate_season(season)
    console.print(f"[bold green]Done![/bold green] Created {count} trend snapshots.")

    if compare_to:
        prev = get_season_by_code(compare_to)
        if not prev:
            console.print(f"[red]Comparison season '{compare_to}' not found.[/red]")
            raise SystemExit(1)
        console.print(f"Comparing [cyan]{season}[/cyan] vs [cyan]{compare_to}[/cyan]...")
        results = compare_seasons(season, compare_to)

        dirs = {}
        for r in results:
            dirs[r["direction"]] = dirs.get(r["direction"], 0) + 1
        console.print(f"  [green]UP: {dirs.get('up', 0)}[/green]  "
                       f"[red]DOWN: {dirs.get('down', 0)}[/red]  "
                       f"[yellow]STABLE: {dirs.get('stable', 0)}[/yellow]  "
                       f"[cyan]NEW: {dirs.get('new', 0)}[/cyan]  "
                       f"[dim]GONE: {dirs.get('gone', 0)}[/dim]")


@trends.command("report")
@click.option("--season", required=True, help="Season code, e.g. SS26")
@click.option("--compare-to", default=None, help="Previous season for direction arrows")
@click.option("--attribute", default=None, help="Filter to a single attribute type")
@click.option("--top", default=10, type=int, help="Show top N values per attribute")
def trends_report(season, compare_to, attribute, top):
    """Show trend report with Rich tables."""
    from storage.database import get_trend_snapshots, get_season_by_code

    s = get_season_by_code(season)
    if not s:
        console.print(f"[red]Season '{season}' not found.[/red]")
        raise SystemExit(1)

    snaps = get_trend_snapshots(season)
    if not snaps:
        console.print(f"[yellow]No snapshots for {season}. Run 'trends aggregate' first.[/yellow]")
        return

    # Group by attribute type
    grouped: dict[str, list[dict]] = {}
    for snap in snaps:
        at = snap["attribute_type"]
        if attribute and at != attribute:
            continue
        grouped.setdefault(at, []).append(snap)

    direction_arrows = {
        "up": "[green]▲[/green]",
        "down": "[red]▼[/red]",
        "stable": "[yellow]—[/yellow]",
        "new": "[cyan]★[/cyan]",
        "gone": "[dim]✕[/dim]",
    }

    for attr_type, values in grouped.items():
        # Sort by frequency desc, take top N
        values.sort(key=lambda x: x["frequency"], reverse=True)
        values = values[:top]

        total = values[0]["total_looks"] if values else 0

        t = Table(title=f"{attr_type} ({season})")
        t.add_column("Value", style="cyan")
        t.add_column("Freq", style="green", justify="right")
        t.add_column("Pct", style="yellow", justify="right")
        if compare_to:
            t.add_column("Dir", justify="center")
            t.add_column("Change", justify="right")

        for v in values:
            pct = f"{(v['frequency'] / total * 100):.1f}%" if total else "—"
            row = [v["attribute_value"], str(v["frequency"]), pct]
            if compare_to:
                d = v.get("direction") or "—"
                arrow = direction_arrows.get(d, d)
                cp = v.get("change_pct")
                change_str = f"{cp:+.1f}pp" if cp is not None else "—"
                row.extend([arrow, change_str])
            t.add_row(*row)

        console.print(t)
        console.print()


@trends.command("clear")
@click.option("--season", required=True, help="Season code to clear")
def trends_clear(season):
    """Clear trend snapshots for a season."""
    from storage.database import clear_trend_snapshots
    count = clear_trend_snapshots(season)
    console.print(f"Cleared {count} snapshots for [cyan]{season}[/cyan].")


# ── Dashboard command ─────────────────────────────────────────────────────────


@cli.command("dashboard")
def dashboard():
    """Launch the Streamlit dashboard."""
    import subprocess
    subprocess.run(
        [sys.executable, "-m", "streamlit", "run", "dashboard/app.py",
         "--server.port", str(DASHBOARD_PORT),
         "--server.headless", "true"],
        check=True,
    )
