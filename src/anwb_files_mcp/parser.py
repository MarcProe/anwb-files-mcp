"""Defensieve omzetting van de ruwe ``__NEXT_DATA__``-payload naar onze modellen.

Het exacte pad naar de data binnen ``__NEXT_DATA__`` is *niet* stabiel: het
ligt diep in ``props.pageProps.loaderData.<uuid>.dehydratedState.queries[].
state.data`` en de UUID verandert. Daarom doorzoeken we de hele structuur
naar een dict die de kenmerkende sleutels ``roads`` (lijst) en ``totals``
(richting) bevat, i.p.v. een star pad te volgen.
"""

from __future__ import annotations

from typing import Any, Optional

from .client import _now_iso, FILELIJST_URL
from .errors import StructureError
from .models import Filelijst, Road, Totals

# Sleutels die samen wijzen op de filelijst-data.
_DATA_KEYS = {"roads", "totals"}


def _find_data_node(obj: Any) -> Optional[dict[str, Any]]:
    """Zoek recursief de eerste dict met zowel ``roads`` als ``totals``."""
    if isinstance(obj, dict):
        if _DATA_KEYS.issubset(obj.keys()) and isinstance(obj.get("roads"), list):
            return obj
        for value in obj.values():
            found = _find_data_node(value)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_data_node(item)
            if found is not None:
                return found
    return None


def parse_next_data(next_data: dict[str, Any]) -> Filelijst:
    """Zet de ruwe ``__NEXT_DATA__``-payload om naar een :class:`Filelijst`.

    Raises
    ------
    StructureError
        Als de data-niet kan worden gevonden of de wegenlijst leeg is.
    """
    node = _find_data_node(next_data)
    if node is None:
        raise StructureError(
            "Kon de filelijst-data (roads/totals) in de pagina niet vinden. "
            "De structuur is waarschijnlijk gewijzigd."
        )

    roads_raw = node.get("roads") or []
    if not roads_raw:
        raise StructureError("De filelijst bevat geen wegen (roads is leeg).")

    roads: list[Road] = []
    for road_raw in roads_raw:
        # ``segments`` is in de bron een lijst van lijsten; weflatten we die.
        raw_segments: list[dict[str, Any]] = []
        for seg_group in road_raw.get("segments") or []:
            if isinstance(seg_group, list):
                raw_segments.extend(seg_group)
            elif isinstance(seg_group, dict):
                raw_segments.append(seg_group)

        roads.append(
            Road(
                road=str(road_raw.get("road", "")),
                type=str(road_raw.get("type", "a")),
                segments=[dict(s) for s in raw_segments],
            )
        )

    totals: Optional[Totals] = None
    if node.get("totals"):
        totals = Totals(**node["totals"])

    return Filelijst(
        roads=roads,
        totals=totals,
        fetched_at=_now_iso(),
        source_url=FILELIJST_URL,
    )


def parse_html(html: str) -> Filelijst:
    """Handige helper: HTML -> __NEXT_DATA__ -> Filelijst (geen netwerk).

    Nuttig voor tests met een lokaal fixture-bestand.
    """
    from .client import FilelijstClient

    return parse_next_data(FilelijstClient.extract_next_data(html))


__all__ = ["parse_next_data", "parse_html", "_find_data_node"]
