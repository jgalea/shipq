import json
import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from typing import Optional

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from . import geo
from .models import Parcel, Place, ShipError
from .providers import eurosender, packlink

PROVIDERS = {"packlink": packlink, "eurosender": eurosender}

app = typer.Typer(add_completion=False, no_args_is_help=True,
                  help="Compare parcel shipping quotes across courier aggregators.")
console = Console()
err = Console(stderr=True)


def _place(s: str) -> Place:
    m = re.fullmatch(r"([A-Za-z]{2})[:/ ](.+)", s.strip())
    if not m:
        raise typer.BadParameter(f"{s!r}: use COUNTRY:POSTCODE, e.g. PT:1100-148")
    return Place(m[1].upper(), m[2].strip())


def _size(s: str) -> tuple[float, float, float]:
    parts = re.split(r"\s*[x×*,]\s*", s.strip().lower())
    if len(parts) != 3:
        raise typer.BadParameter("--size takes LxWxH in cm, e.g. 60x30x20")
    return tuple(float(x) for x in parts)


def _nearest(points, here, radius):
    for d in points:
        d.distance_m = geo.distance_m(here[0], here[1], d.lat, d.lon)
    points.sort(key=lambda d: d.distance_m)
    return [d for d in points if radius is None or d.distance_m <= radius]


@app.command()
def quote(
    origin: str = typer.Argument(..., help="COUNTRY:POSTCODE, e.g. PT:1100-148"),
    dest: str = typer.Argument(..., help="COUNTRY:POSTCODE, e.g. SK:81101"),
    weight: float = typer.Option(..., "--weight", "-w", help="kg"),
    size: str = typer.Option(..., "--size", "-s", help="LxWxH in cm"),
    pickup: bool = typer.Option(False, "--pickup", help="Only services that collect from your door"),
    dropoff: bool = typer.Option(False, "--dropoff", help="Only services you drop off at a point"),
    near: Optional[str] = typer.Option(None, "--near", help="lat,lon or an address; finds the closest drop-off point"),
    radius: Optional[float] = typer.Option(None, "--radius", "-r", help="Metres from --near; hides drop-off services with no point that close"),
    to_shop: bool = typer.Option(False, "--to-shop", help="Include services that deliver to a parcel shop instead of the address"),
    providers: str = typer.Option(",".join(PROVIDERS), "--providers", "-p"),
    as_json: bool = typer.Option(False, "--json"),
):
    """Quote one parcel across every provider, cheapest first."""
    if pickup and dropoff:
        raise typer.BadParameter("pick one of --pickup or --dropoff")
    src, dst = _place(origin), _place(dest)
    parcel = Parcel(weight, *_size(size))
    names = [n.strip() for n in providers.split(",") if n.strip()]
    if unknown := [n for n in names if n not in PROVIDERS]:
        raise typer.BadParameter(f"unknown provider {', '.join(unknown)}; have {', '.join(PROVIDERS)}")

    quotes, failed = [], {}
    with ThreadPoolExecutor() as pool:
        futures = {n: pool.submit(PROVIDERS[n].quotes, src, dst, parcel) for n in names}
        for n, f in futures.items():
            try:
                quotes += f.result()
            except ShipError as e:
                failed[n] = str(e)
    if not to_shop:
        quotes = [q for q in quotes if not q.to_shop]
    if pickup:
        quotes = [q for q in quotes if q.pickup]
    if dropoff:
        quotes = [q for q in quotes if not q.pickup]

    nearest = {}
    if near:
        here = geo.locate(near)
        for q in [q for q in quotes if not q.pickup]:
            if q.provider != "packlink":
                nearest[id(q)] = None  # point lists aren't exposed without starting an order
                continue
            try:
                pts = _nearest(packlink.dropoffs(q.service_id, src), here, radius)
            except ShipError as e:
                failed[f"packlink dropoffs {q.service_id}"] = str(e)
                nearest[id(q)] = None
                continue
            nearest[id(q)] = pts[0] if pts else False
        if radius is not None:
            quotes = [q for q in quotes if q.pickup or nearest.get(id(q)) is not False]
    quotes.sort(key=lambda q: q.price)

    if as_json:
        rows = []
        for q in quotes:
            row = asdict(q)
            pt = nearest.get(id(q))
            row["nearest_point"] = asdict(pt) if pt else None
            rows.append(row)
        print(json.dumps({"parcel": {**asdict(parcel), "billable_kg": round(parcel.billable, 2)},
                          "quotes": rows, "errors": failed}, ensure_ascii=False, indent=2))
        return

    for n, e in failed.items():
        err.print(f"[yellow]{n}: {escape(e)}[/yellow]")
    if not quotes:
        console.print("No services found.")
        raise typer.Exit(1)

    vol = parcel.volumetric
    title = (f"{src.country} {src.zip} → {dst.country} {dst.zip}, {parcel.weight:g} kg, "
             f"{parcel.length:g}×{parcel.width:g}×{parcel.height:g} cm")
    if vol > parcel.weight:
        title += f" (bills as {vol:.1f} kg volumetric)"
    t = Table(title=escape(title))
    t.add_column("Price", justify="right", no_wrap=True)
    t.add_column("Via", no_wrap=True)
    t.add_column("Carrier / service", overflow="fold")
    t.add_column("Collection", no_wrap=True)
    t.add_column("Transit", no_wrap=True)
    t.add_column("Notes", overflow="fold")
    for q in quotes:
        coll = "[green]home pickup[/green]" if q.pickup else "drop-off"
        notes = [escape(n) for n in q.notes]
        if id(q) in nearest:
            pt = nearest[id(q)]
            if pt:
                notes.insert(0, f"[cyan]{pt.distance_m:.0f} m: {escape(pt.name)}, {escape(pt.address)}[/cyan]")
            elif pt is None:
                notes.insert(0, "drop-off points not listed")
        if q.label_required:
            notes.append("print label")
        service = escape(f"{q.service} (to shop)" if q.to_shop else q.service)
        t.add_row(f"€{q.price:.2f}", q.provider, f"{escape(q.carrier)}: {service}",
                  coll, escape(q.days), "; ".join(notes))
    console.print(t)
    console.print("[dim]Prices include VAT.[/dim]")


@app.command()
def points(
    service_id: str = typer.Argument(..., help="Packlink service id (shipq quote --json shows it)"),
    origin: str = typer.Argument(..., help="COUNTRY:POSTCODE to search around"),
    near: Optional[str] = typer.Option(None, "--near", help="lat,lon or an address to measure distance from"),
    radius: Optional[float] = typer.Option(None, "--radius", "-r", help="Metres from --near"),
    limit: int = typer.Option(15, "--limit", "-l"),
    as_json: bool = typer.Option(False, "--json"),
):
    """List drop-off points for a Packlink service."""
    pts = packlink.dropoffs(service_id, _place(origin))
    if near:
        pts = _nearest(pts, geo.locate(near), radius)
    pts = pts[:limit]
    if as_json:
        print(json.dumps([asdict(p) for p in pts], ensure_ascii=False, indent=2))
        return
    if not pts:
        console.print("No drop-off points" + (f" within {radius:g} m." if radius else "."))
        raise typer.Exit(1)
    t = Table()
    if near:
        t.add_column("Dist.", justify="right", no_wrap=True)
    t.add_column("Point", overflow="fold")
    t.add_column("Address", overflow="fold")
    t.add_column("Mon-Fri", no_wrap=True)
    t.add_column("Sat", no_wrap=True)
    for p in pts:
        row = [escape(p.name), escape(f"{p.address}, {p.zip} {p.city}"), escape(p.hours.get("monday", "-")), escape(p.hours.get("saturday", "-"))]
        if near:
            row.insert(0, f"{p.distance_m:.0f} m")
        t.add_row(*row)
    console.print(t)


def main():
    try:
        app()
    except ShipError as e:
        err.print(f"[red]{escape(str(e))}[/red]")
        raise SystemExit(1)
