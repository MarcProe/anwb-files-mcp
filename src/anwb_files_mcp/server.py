"""Stdio-MCP-server die de ANWB-filelijst als gestructureerde tools aanbiedt.

Uitvoeren: ``anwb-files-mcp`` (zie ``[project.scripts]`` in pyproject.toml).
De server spreekt het MCP-stdio-protocol en levert op elk verzoek een verse
snapshot van de filelijst (er is geen cache; de bron zelf update continu).
"""

from __future__ import annotations

import sys
from typing import Any, Literal, Optional

from mcp.server.fastmcp import FastMCP

from .client import FilelijstClient
from .errors import FetchError, StructureError
from .models import Filelijst, Segment
from .parser import parse_next_data

# Snelweg- of N-wegnummer als "A12" / "N322" (case-insensitief bij de match).
RoadRef = str

mcp = FastMCP(
    "anwb-files-mcp",
    instructions=(
        "Structuur aan filelijst van de ANWB (Nederland): staus, files, "
        "werkzaamheden, flitsers en wegafsluitingen per weg. Data is afgeleid "
        "van https://www.anwb.nl/verkeer/filelijst en ververst per aanvraag. "
        "Vertragingen in minuten, afstanden in kilometers/meters."
    ),
)

# Alle categorieën die de site kent.
ALL_CATEGORIES = ("jams", "road-closed", "roadworks", "radars")


# ---------------------------------------------------------------------------
# Interne helpers
# ---------------------------------------------------------------------------
def _client() -> FilelijstClient:
    """Frisse client per aanroep (geen gedeelde staat tussen tools)."""
    return FilelijstClient()


def _load() -> Filelijst:
    """Haal de filelijst op en parse deze. Gooi een heldere fout bij falen."""
    try:
        next_data = _client().fetch()
    except FetchError as exc:
        raise RuntimeError(f"Ophalen mislukt: {exc}") from exc
    except StructureError as exc:
        raise RuntimeError(f"Parsen mislukt: {exc}") from exc
    try:
        return parse_next_data(next_data)
    except StructureError as exc:
        raise RuntimeError(f"Parsen mislukt: {exc}") from exc


def _normalise_road(road: Optional[str]) -> Optional[str]:
    """Normaliseer een wegnamen ("a12" -> "A12", "12" -> "A12")."""
    if road is None:
        return None
    r = road.strip().upper()
    if r.isdigit():
        r = "A" + r
    return r


def _iter_segments(files: Filelijst):
    """Itereer over alle segmenten van alle wegen (met wegnummer)."""
    for road in files.roads:
        for seg in road.segments:
            yield road.road, seg


def _filter(
    files: Filelijst,
    category: Optional[str],
    road: Optional[str],
    min_delay_min: Optional[float],
    max_results: int,
):
    """Filter en sorteer segmenten op (categorij, weg, min. vertraging)."""
    road = _normalise_road(road)
    out: list[Segment] = []
    for road_name, seg in _iter_segments(files):
        if category and seg.category != category:
            continue
        if road and road_name != road:
            continue
        if min_delay_min is not None:
            dm = seg.delay_minutes
            if dm is None or dm < min_delay_min:
                continue
        out.append(seg)

    # Sorteer: op vertraging aflopend (None komt laatste), dan op wegnummer.
    def _key(s: Segment):
        return (-(s.delay_minutes or 0), s.road, s.from_)

    out.sort(key=_key)
    return out[:max_results]


def _seg_dict(seg: Segment) -> dict[str, Any]:
    """Zet een Segment om naar een compact, MCP-vriendelijke dict."""
    return {
        "id": seg.id,
        "road": seg.road,
        "segmentId": seg.segment_id,
        "category": seg.category,
        "incidentType": seg.incident_type,
        "from": seg.from_,
        "to": seg.to,
        "reason": seg.reason,
        "delayMinutes": seg.delay_minutes,
        "distanceM": seg.distance_m,
        "distanceKm": seg.delay_km,
        "start": seg.start,
        "hm": seg.hm,
        "direction": seg.code_direction,
        "events": [
            {"alertC": e.alert_c, "text": e.text, "distanceM": e.distance_m}
            for e in seg.events
        ],
        "location": _loc(seg),
    }


def _loc(seg: Segment) -> Optional[dict[str, float]]:
    """Geef het beste beschikbare punt (coordinates > loc > van)."""
    if seg.coordinates is not None:
        return {"lat": seg.coordinates.latitude, "lon": seg.coordinates.longitude}
    if seg.loc is not None:
        return {"lat": seg.loc.lat, "lon": seg.loc.lon}
    if seg.from_loc is not None:
        return {"lat": seg.from_loc.lat, "lon": seg.from_loc.lon}
    return None


def _error_message(exc: Exception) -> dict[str, Any]:
    """Formateer een fout als een consistent, afleesbaar object."""
    return {
        "error": type(exc).__name__,
        "message": str(exc),
        "hint": (
            "Probeer het over een paar seconden opnieuw; ANWB kan tijdelijk "
            "beschikbaar zijn of de paginastructuur kan zijn gewijzigd."
        ),
    }


# ---------------------------------------------------------------------------
# MCP-tools
# ---------------------------------------------------------------------------
@mcp.tool()
def get_totals() -> dict[str, Any]:
    """Landelijke filelijst-totaaltallen per wegtyp (snelweg A, N-weg, totaal).

    Geeft voor elk type de totale file-afstand (km), totale vertraging (minuten)
    en het aantal actieve files. Dit is de goedkoopste methode voor een
    landelijk overzicht.

    Returns
    -------
    dict
        ``{"a": {...}, "n": {...}, "other": {...}, "all": {...}, "fetchedAt": ...}``
        met per item ``distanceKm``, ``delayMinutes`` en ``count``.
    """
    try:
        files = _load()
        t = files.totals
        def _block(x):
            return (
                {
                    "distanceKm": x.distance_km,
                    "delayMinutes": x.delay_minutes,
                    "count": x.count,
                }
                if x
                else None
            )
        return {
            "a": _block(t.a if t else None),
            "n": _block(t.n if t else None),
            "other": _block(t.other if t else None),
            "all": _block(t.all_ if t else None),
            "fetchedAt": files.fetched_at,
            "sourceUrl": files.source_url,
        }
    except Exception as exc:  # noqa: BLE001 - we geven een nette tool-fout
        return _error_message(exc)


@mcp.tool()
def get_files(
    road: Optional[str] = None,
    min_delay_min: float = 0.0,
    max_results: int = 50,
) -> dict[str, Any]:
    """Alle actieve files (staus) met vertraging, lengte en reden.

    Parameters
    ----------
    road:
        Optioneel wegnamen, bijv. ``"A12"`` of ``"N322"``. Zonder filter alle wegen.
    min_delay_min:
        Alleen files met minstens deze vertraging in minuten (standaard 0 = allemaal).
    max_results:
        Maximum aantal resultaten, gesorteerd op vertraging (meest verstoring bovenin).

    Returns
    -------
    dict
        ``{"count": N, "files": [...], "fetchedAt": ...}``. Elke file bevat o.a.
        ``road``, ``from``, ``to``, ``reason`` (NL), ``delayMinutes``, ``distanceKm``.
    """
    try:
        files = _load()
        segs = _filter(files, category="jams", road=road, min_delay_min=min_delay_min,
                       max_results=max_results)
        return {
            "count": len(segs),
            "files": [_seg_dict(s) for s in segs],
            "fetchedAt": files.fetched_at,
            "sourceUrl": files.source_url,
        }
    except Exception as exc:  # noqa: BLE001
        return _error_message(exc)


@mcp.tool()
def get_incidents(
    category: Literal["jams", "road-closed", "roadworks", "radars"] = "jams",
    road: Optional[str] = None,
    max_results: int = 50,
) -> dict[str, Any]:
    """Verkeersincidenten van een bepaalde categorie.

    Categorieën: ``jams`` (files/staus), ``road-closed`` (weg afgesloten),
    ``roadworks`` (werkzaamheden) en ``radars`` (flitsers).

    Parameters
    ----------
    category:
        Type incident (standaard ``jams``).
    road:
        Optioneel wegnamen (bijv. ``"A15"``).
    max_results:
        Maximum aantal resultaten.
    """
    try:
        files = _load()
        segs = _filter(files, category=category, road=road, min_delay_min=None,
                       max_results=max_results)
        return {
            "category": category,
            "count": len(segs),
            "incidents": [_seg_dict(s) for s in segs],
            "fetchedAt": files.fetched_at,
            "sourceUrl": files.source_url,
        }
    except Exception as exc:  # noqa: BLE001
        return _error_message(exc)


@mcp.tool()
def get_road(road: str) -> dict[str, Any]:
    """Alle filelijst-segmenten voor één weg, over alle categorieën.

    Parameters
    ----------
    road:
        Wegnummer, bijv. ``"A12"`` of ``"N322"``.
    """
    try:
        files = _load()
        road_n = _normalise_road(road)
        matches = [r for r in files.roads if r.road == road_n]
        if not matches:
            return {
                "road": road_n,
                "found": False,
                "segments": [],
                "message": f"Geen actuele filelijst-segmenten voor {road_n}.",
                "fetchedAt": files.fetched_at,
            }
        r = matches[0]
        by_cat: dict[str, list[dict[str, Any]]] = {}
        for seg in r.segments:
            by_cat.setdefault(seg.category or "onbekend", []).append(_seg_dict(seg))
        return {
            "road": r.road,
            "type": r.type,
            "found": True,
            "segmentCount": len(r.segments),
            "byCategory": by_cat,
            "fetchedAt": files.fetched_at,
        }
    except Exception as exc:  # noqa: BLE001
        return _error_message(exc)


@mcp.tool()
def get_raw() -> dict[str, Any]:
    """Het volledige, ongefilterde filelijst-JSON (voor debugging / power users).

    Levert alle wegen met alle segmenten en de landelijke totalen, zo dicht
    mogelijk bij de bron (nederlandse tekstvelden blijven behouden).
    """
    try:
        files = _load()
        payload = files.model_dump(by_alias=True)
        # Coördinaten/limits zijn al LatLng; model_dump geeft dict's terug.
        return payload
    except Exception as exc:  # noqa: BLE001
        return _error_message(exc)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    """Start de stdio-MCP-server (ook via ``anwb-files-mcp``).

    Bij een stdio-server moet ``stdout`` puur het JSON-RPC-protocol bevatten.
    Logboeken (o.a. ``httpx`` en de MCP-server zelf) schrijven naar ``stderr``,
    maar we zetten ze expliciet op WARNING zodat stderr niet vol ruis loopt
    (``HTTP Request: ...`` / ``Processing request: ...``).
    """
    import logging

    logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
    for noisy in ("httpx", "httpcore", "mcp.server"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    mcp.run()


if __name__ == "__main__":
    main()


__all__ = ["mcp", "main", "get_totals", "get_files", "get_incidents", "get_road", "get_raw"]
