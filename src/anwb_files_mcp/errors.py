"""Fouten die door de client- en parserlaag kunnen worden opgeworpen."""


class FetchError(Exception):
    """Het ophalen van de filelijst-pagina is mislukt (netwerk- of HTTP-probleem)."""


class StructureError(Exception):
    """De verwachte datastructuur in de pagina is niet gevonden.

    De pagina is een Next.js-app; de interne structuur (o.a. de
    ``__NEXT_DATA__``-blokken en de paden daarin) kan gewijzigd worden.
    Deze fout geeft aan dat de data niet langer op de bekende plek staat,
    zodat de aanroeper een heldere melding kan geven i.p.v. een lege lijst.
    """
