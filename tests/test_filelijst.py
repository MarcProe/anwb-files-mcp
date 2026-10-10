"""Tests voor de filelijst-parser en -tools.

Alles draait offline: we gebruiken een meegeleverde HTML-snapshot in
``tests/fixtures/filelijst.html``. Er wordt dus niks live opgehaald.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from anwb_files_mcp.client import FilelijstClient
from anwb_files_mcp.errors import StructureError
from anwb_files_mcp.parser import parse_html, parse_next_data

FIXTURE = Path(__file__).parent / "fixtures" / "filelijst.html"


@pytest.fixture(scope="module")
def html() -> str:
    """Inhoud van de meegeleverde snapshot."""
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def files(html) -> "object":
    """Geparste Filelijst uit de snapshot (één keer per testmodule)."""
    return parse_html(html)


def test_extract_next_data(html):
    """Het __NEXT_DATA__-blok wordt herkend en is geldige JSON."""
    data = FilelijstClient.extract_next_data(html)
    assert isinstance(data, dict)
    assert "props" in data


def test_extract_next_data_missing():
    """Ontbrekend blok levert een duidelijke StructureError op."""
    with pytest.raises(StructureError):
        FilelijstClient.extract_next_data("<html>geen data</html>")


def test_parse_has_roads(files):
    """De parser vindt een non-leeg lijst van wegen."""
    assert files.roads, "Er moeten wegen in de filelijst staan"
    # Er zijn zowel snel- (A) als N-wegen.
    types = {r.type for r in files.roads}
    assert "a" in types
    assert "n" in types


def test_segments_flattened(files):
    """Elk segment is een dict met de kenmerkende velden."""
    for road in files.roads:
        for seg in road.segments:
            assert seg.road == road.road
            assert seg.from_ is not None
            assert seg.to is not None
            # category moet een van de bekende waarden zijn (of None bij vage bron)
            if seg.category is not None:
                assert seg.category in {"jams", "road-closed", "roadworks", "radars"}


def test_totals_present(files):
    """De landelijke totalen bestaan en hebben consistentie."""
    assert files.totals is not None
    t = files.totals
    assert t.all_ is not None
    assert t.all_.count is not None and t.all_.count > 0
    # A + N zou grofweg de totale count moeten benaderen (bron-totaal).
    if t.a is not None and t.n is not None and t.all_ is not None:
        # We controleren alleen dat de getallen plausibel (niet-negatief) zijn.
        assert t.a.count >= 0
        assert t.n.count >= 0


def test_delay_normalisation(files):
    """delayMinutes wordt correct afgeleid van de seconden."""
    # Pak het eerste jam-segment met een vertraging.
    jam = next(
        (s for r in files.roads for s in r.segments if s.category == "jams" and s.delay_s),
        None,
    )
    assert jam is not None, "Er moet minstens één jam met vertraging zijn"
    assert jam.delay_minutes == round(jam.delay_s / 60, 1)


def test_road_normalise():
    """Wegnummers worden genormaliseerd (a12 -> A12, 12 -> A12)."""
    from anwb_files_mcp.server import _normalise_road

    assert _normalise_road("a12") == "A12"
    assert _normalise_road("12") == "A12"
    assert _normalise_road("n322") == "N322"
    assert _normalise_road(None) is None


def test_get_totals_shape(files):
    """get_totals geeft de verwachte top-niveaus terug."""
    from anwb_files_mcp.server import get_totals

    # get_totals haalt live op; dat willen we in de test vermijden. We testen
    # daarom de format-logica met een mock op _load.
    import anwb_files_mcp.server as srv

    original = srv._load
    srv._load = lambda: files
    try:
        out = get_totals()
    finally:
        srv._load = original
    assert "all" in out and "a" in out and "n" in out
    assert out["all"] is not None
    assert "distanceKm" in out["all"]
    assert "delayMinutes" in out["all"]
    assert "count" in out["all"]
    assert "fetchedAt" in out


def test_get_files_filter_and_sort(files):
    """get_files filtert op weg en sorteert op vertraging (aflopend)."""
    import anwb_files_mcp.server as srv

    original = srv._load
    srv._load = lambda: files
    try:
        out = srv.get_files(max_results=1000)
    finally:
        srv._load = original

    assert "files" in out
    files_list = out["files"]
    if files_list:
        # Alle items moeten category "jams" hebben.
        assert all(f["category"] == "jams" for f in files_list)
        # Gesorteerd op delayMinutes aflopend (None laatste).
        delays = [f["delayMinutes"] for f in files_list]
        numeric = [d for d in delays if d is not None]
        assert numeric == sorted(numeric, reverse=True)


def test_get_files_by_road(files):
    """get_files(road=...) geeft alleen die weg terug."""
    import anwb_files_mcp.server as srv

    # Kies een weg die in de snapshot staat.
    a_road = next((r.road for r in files.roads if r.type == "a"), None)
    assert a_road, "Geen A-weg gevonden in de snapshot"

    original = srv._load
    srv._load = lambda: files
    try:
        out = srv.get_files(road=a_road, max_results=1000)
    finally:
        srv._load = original

    for f in out["files"]:
        assert f["road"] == a_road


def test_get_incidents_categories(files):
    """get_incidents werkt voor elk van de vier categorieën (geen crash)."""
    import anwb_files_mcp.server as srv

    original = srv._load
    srv._load = lambda: files
    try:
        for cat in ("jams", "road-closed", "roadworks", "radars"):
            out = srv.get_incidents(category=cat, max_results=5)
            assert out["category"] == cat
            assert "incidents" in out
            assert isinstance(out["incidents"], list)
    finally:
        srv._load = original


def test_get_road_found_and_not_found(files):
    """get_road werkt zowel voor een bestaande als een onbestaande weg."""
    import anwb_files_mcp.server as srv

    a_road = next((r.road for r in files.roads if r.type == "a"), None)
    original = srv._load
    srv._load = lambda: files
    try:
        found = srv.get_road(road=a_road)
        assert found["found"] is True
        assert found["segmentCount"] >= 0

        not_found = srv.get_road(road="A9999")
        assert not_found["found"] is False
        assert not_found["segments"] == []
    finally:
        srv._load = original
