"""Ophalen van de ANWB-filelijstpagina en extractie van de ``__NEXT_DATA__``-payload.

De filelijst is een Next.js-app. De echte data staat verwerkt in het
``<script id="__NEXT_DATA__" type="application/json">``-blok in de HTML.
We hebben dus geen API-key nodig: we halen de HTML op en parsen dat blok.

Let op: ``__NEXT_DATA__`` is een interne Next.js-mechanisme en geen stabiel
open API. Het pad naar de data binnen dit blok kan veranderen; daarom
zoekt :func:`extract_next_data` op structuur i.p.v. op een star pad (zie
:mod:`anwb_files_mcp.parser`).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any, Optional

import httpx

from .errors import FetchError, StructureError

# De pagina met de filelijst.
FILELIJST_URL = "https://www.anwb.nl/verkeer/filelijst"

# Browser-achtige user-agent: de server levert de volledige __NEXT_DATA__-payload
# alleen aan voor een "echte" browser. Een kale Python-User-Agent levert een
# afgeslankte pagina zonder de data.
USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Regels voor het __NEXT_DATA__-blok.
_NEXT_DATA_RE = re.compile(
    r'<script\s+id="__NEXT_DATA__"\s+type="application/json">(.*?)</script>',
    re.DOTALL,
)


class FilelijstClient:
    """Kleine wrapper om de filelijst op te halen en te ontleden.

    Parameters
    ----------
    base_url:
        Standaard :data:`FILELIJST_URL`. Kan worden overriden in tests.
    timeout:
        Request-timeout in seconden.
    """

    def __init__(
        self,
        base_url: str = FILELIJST_URL,
        timeout: float = 25.0,
        user_agent: str = USER_AGENT,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.user_agent = user_agent

    def fetch_html(self) -> str:
        """Haal de HTML van de filelijst op (met één retry bij 5xx/time-out)."""
        last_error: Optional[Exception] = None
        for attempt in range(2):
            try:
                with httpx.Client(
                    timeout=self.timeout,
                    follow_redirects=True,
                    headers={
                        "User-Agent": self.user_agent,
                        "Accept": "text/html,application/xhtml+xml",
                        "Accept-Language": "nl-NL,nl;q=0.9",
                    },
                ) as client:
                    resp = client.get(self.base_url)
                    if resp.status_code >= 500:
                        raise FetchError(
                            f"Serverfout {resp.status_code} bij het ophalen van {self.base_url}"
                        )
                    resp.raise_for_status()
                    return resp.text
            except (httpx.HTTPError, FetchError) as exc:
                last_error = exc
                # Eén keer opnieuw proberen bij tijdelijke fouten.
                continue
        raise FetchError(
            f"Kon de filelijst niet ophalen van {self.base_url}: {last_error}"
        )

    @staticmethod
    def extract_next_data(html: str) -> dict[str, Any]:
        """Ontleed het ``__NEXT_DATA__``-JSON-blok uit de HTML.

        Dit is bewust een aparte, statische methode zodat tests een lokaal
        HTML-bestand (fixture) kunnen doorgeven zonder netwerkverkeer.

        Raises
        ------
        StructureError
            Als het blok ontbreekt of niet valide JSON is.
        """
        match = _NEXT_DATA_RE.search(html)
        if not match:
            raise StructureError(
                "Kon het __NEXT_DATA__-blok in de pagina niet vinden. "
                "De pagina is waarschijnlijk gewijzigd of er is een anti-bot-blok. "
                "Controleer of de browser-User-Agent wordt meegestuurd."
            )
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError as exc:
            raise StructureError(f"__NEXT_DATA__ is geen geldige JSON: {exc}") from exc

    def fetch(self) -> dict[str, Any]:
        """Haal de pagina op en geef de ruwe ``__NEXT_DATA__``-payload terug.

        De payload wordt doorgegeven naar :func:`anwb_files_mcp.parser.parse_next_data`.
        """
        return self.extract_next_data(self.fetch_html())


def _now_iso() -> str:
    """Huidige UTC-tijd als ISO 8601-reeks (seconden-nauwkeurigheid)."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


__all__ = [
    "FilelijstClient",
    "FILELIJST_URL",
    "USER_AGENT",
    "_now_iso",
]
