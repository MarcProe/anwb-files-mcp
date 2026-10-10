"""Pydantic-modellen voor de filelijst-data.

De bron is de ``__NEXT_DATA__``-payload van de ANWB-filelijstpagina.
We houden de oorspronkelijke Nederlandse tekstvelden (``reason``,
``events``) ongewijzigd en normaliseren alleen een paar dingen:

* ``delay`` komt in seconden -> we vatten ook ``delay_minutes`` af;
* ``distance`` blijft in meters;
* coördinaten en bbox worden geverifieerd.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# Mogelijke segment-categorieën (veld ``category`` in de bron).
Category = Literal["jams", "road-closed", "roadworks", "radars"]

# Mogelijke incidenttypes (veld ``incidentType`` in de bron).
IncidentType = Literal[
    "slow-traffic",
    "queing-traffic",
    "stationary-traffic",
    "road-closed",
    "roadworks",
    "radar",
    "unknown",
]


class LatLng(BaseModel):
    """Een lat/lon-punt in de vorm ``{lat, lon}`` (gebruikt door fromLoc/toLoc/loc)."""

    lat: float
    lon: float


class Coordinates(BaseModel):
    """Een punt in de vorm ``{latitude, longitude}`` (gebruikt door het veld ``coordinates``)."""

    latitude: float
    longitude: float


class Bounds(BaseModel):
    """Omgevingsrechthoek (bounding box) van een segment."""

    south_west: LatLng = Field(alias="southWest")
    north_east: LatLng = Field(alias="northEast")


class Event(BaseModel):
    """Een individueel verkeersevenement binnen een segment.

    ``alertC`` is de (TomTom/ANWB) alert-code, ``text`` de Nederlandse
    beschrijving en ``distance`` de lengte in meters (niet altijd aanwezig).
    """

    alert_c: int = Field(alias="alertC")
    text: str
    distance_m: Optional[int] = Field(default=None, alias="distance")


class Segment(BaseModel):
    """Een filelijst-segment (de kern-eenheid).

    Combineert wat de ANWB op de site toont (van->naar, vertraging,
    lengte, reden) met de ruwe metadata (id's, coördinaten, polyline).
    """

    # Identificatie
    id: Optional[int] = None
    road: str
    segment_id: Optional[int] = Field(default=None, alias="segmentId")
    code_direction: Optional[int] = Field(default=None, alias="codeDirection")
    afrc: Optional[int] = None

    # Categorie & type
    category: Optional[Category] = None
    incident_type: Optional[IncidentType] = Field(default=None, alias="incidentType")
    type: Optional[str] = None

    # Locatie
    from_: str = Field(alias="from")
    to: str
    from_loc: Optional[LatLng] = Field(default=None, alias="fromLoc")
    to_loc: Optional[LatLng] = Field(default=None, alias="toLoc")
    loc: Optional[LatLng] = None
    coordinates: Optional[Coordinates] = Field(
        default=None,
        description="Centrale coördinaat (bron gebruikt {latitude, longitude}).",
    )
    bounds: Optional[Bounds] = None

    # Inhoud
    reason: Optional[str] = None
    events: list[Event] = Field(default_factory=list)

    # Meting
    distance_m: Optional[int] = Field(default=None, alias="distance")
    delay_s: Optional[int] = Field(default=None, alias="delay")
    start: Optional[str] = None
    hm: Optional[float] = Field(default=None, alias="HM", description="Hectometerpaal (radars).")

    # Geometrie
    polyline: Optional[str] = None

    model_config = {"populate_by_name": True}

    @property
    def delay_minutes(self) -> Optional[float]:
        """Vertraging in minuten (afgeleid van de seconden in de bron)."""
        if self.delay_s is None:
            return None
        return round(self.delay_s / 60, 1)

    @property
    def delay_km(self) -> Optional[float]:
        """Lengte in kilometers (afgeleid van meters)."""
        if self.distance_m is None:
            return None
        return round(self.distance_m / 1000, 2)


class Road(BaseModel):
    """Een weg (snelweg A* of N-weg) met al zijn filelijst-segmenten."""

    road: str
    type: str = "a"  # "a" = snelweg, "n" = N-weg
    # In de bron is dit een lijst van lijsten; weflatten we het tot één lijst.
    segments: list[Segment] = Field(default_factory=list)


class RoadTotals(BaseModel):
    """Totaal per wegcategorie: afstand, vertraging en aantal files."""

    distance_km: Optional[float] = Field(default=None, alias="distance")
    delay_minutes: Optional[int] = Field(default=None, alias="delay")
    count: Optional[int] = None

    model_config = {"populate_by_name": True}


class Totals(BaseModel):
    """Landelijke totaaltallen zoals de site ze samenvat (a / n / other / all)."""

    a: Optional[RoadTotals] = None
    n: Optional[RoadTotals] = None
    other: Optional[RoadTotals] = None
    all_: Optional[RoadTotals] = Field(default=None, alias="all")

    model_config = {"populate_by_name": True}


class Filelijst(BaseModel):
    """De volledige filelijst: lijst van wegen plus de landelijke totalen."""

    roads: list[Road]
    totals: Optional[Totals] = None
    # Moment van ophalen (ISO 8601, UTC). De bron bevat geen eigen timestamp.
    fetched_at: Optional[str] = None
    source_url: Optional[str] = None
