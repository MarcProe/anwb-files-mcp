# anwb-files-mcp

Een [MCP](https://modelcontextprotocol.io/)-server die de **ANWB-filelijst**
([https://www.anwb.nl/verkeer/filelijst](https://www.anwb.nl/verkeer/filelijst))
leest en als **gestructureerde tools** aanbiedt: staus/files, werkzaamheden,
flitsers en wegafsluitingen per weg, met vertraging, lengte, reden en locatie.

Geschreven in Python (stdio-transport), met `httpx`, `pydantic` en het officiële
`mcp`-SDK. Geen API-key of login nodig.

---

## Hoe het werkt

De filelijst is een **Next.js**-app. De echte data staat verwerkt in het
`<script id="__NEXT_DATA__" type="application/json">`-blok in de HTML.
Deze server:

1. haalt de HTML op (met een browser-achtige User-Agent, want een kale
   `python`-UA levert een afgeslankte pagina zonder data);
2. extrahert het `__NEXT_DATA__`-JSON-blok;
3. zoekt de data op **structuur** (een dict met `roads` + `totals`) i.p.v. op
   een star pad, want het exacte pad en de UUID's daarin veranderen;
4. zet alles om naar nette, geverifieerde Pydantic-modellen.

> **Kanttekening.** `__NEXT_DATA__` is een interne Next.js-mechanisme, géén
> stabiel open API. De site kan de structuur aanpassen. De parser is bewust
> defensief: als de data ontbreekt krijg je een heldere
> `StructureError`/foutmelding in plaats van een lege lijst. De bron zelf is
> ANWB / TomTom.

## Gebruik als MCP-server

De server spreekt het **stdio**-protocol. Sluit hem aan in jouw MCP-client,
bijv. in een client-configuratie:

```json
{
  "mcpServers": {
    "anwb-files": {
      "command": "anwb-files-mcp",
      "args": []
    }
  }
}
```

Na een lokale installatie (zie onder) staat `anwb-files-mcp` op het pad.
Wil je de server direct via `uv` uitvoeren zonder installeren? Dan kun je ook:

```json
{
  "mcpServers": {
    "anwb-files": {
      "command": "uv",
      "args": ["run", "--project", "/pad/naar/anwb-files-mcp", "anwb-files-mcp"]
    }
  }
}
```

### Tools

| Tool | Omschrijving | Belangrijkste parameters |
| --- | --- | --- |
| `get_totals` | Landelijke totalen per wegtyp (A, N, totaal): afstand (km), vertraging (min), aantal files. | – |
| `get_files` | Alle actieve files/staus, gesorteerd op vertraging. | `road`, `min_delay_min`, `max_results` |
| `get_incidents` | Incidenten van één categorie. | `category` (`jams`, `road-closed`, `roadworks`, `radars`), `road`, `max_results` |
| `get_road` | Alle segmenten voor één weg, over alle categorieën. | `road` |
| `get_raw` | Het volledige, ongefilterde filelijst-JSON (debug/power users). | – |

Voorbeelden van aanroepen (zoals een LLM ze zou kunnen stellen):

* `get_files(road="A12", min_delay_min=10)`
* `get_incidents(category="road-closed")`
* `get_road(road="N322")`

### Voorbeeld-output (`get_files`)

```json
{
  "count": 1,
  "files": [
    {
      "id": 29320345,
      "road": "A12",
      "category": "jams",
      "incidentType": "slow-traffic",
      "from": "knp. Oudenrijn",
      "to": "Breukelen",
      "reason": "Door een ongeluk. Dicht. Veiligheidsmaatregelen.",
      "delayMinutes": 9,
      "distanceM": 8300,
      "distanceKm": 8.3,
      "start": "2026-10-10T11:28:00Z",
      "events": [
        { "alertC": 108, "text": "Langzaam rijdend tot stilstaand verkeer", "distanceM": 8300 }
      ],
      "location": { "lat": 52.06562, "lon": 5.07012 }
    }
  ],
  "fetchedAt": "2026-10-10T12:19:00Z",
  "sourceUrl": "https://www.anwb.nl/verkeer/filelijst"
}
```

Tekstvelden (`reason`, `events[].text`) blijven in het **Nederlands**, zoals in
de bron. Eenheden zijn genormaliseerd: vertraging in minuten, lengte in meters
én kilometers.

---

## Locaal installeren & gebruiken

Vereist: Python 3.12+ en [`uv`](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/MarcProe/anwb-files-mcp.git
cd anwb-files-mcp
uv sync --dev
```

### CLI (zonder MCP-client)

```bash
uv run anwb-files totals
uv run anwb-files files --road A12
uv run anwb-files files --min-delay 10 --max 20
uv run anwb-files incidents --category roadworks
uv run anwb-files road A15
uv run anwb-files raw
```

### Testen

De tests draaien **offline** tegen een meegeleverde HTML-snapshot
(`tests/fixtures/filelijst.html`), dus er wordt tijdens `pytest` niets
live opgehaald.

```bash
uv run pytest
```

Een frisse snapshot van de site genereren (optioneel, om de fixture te verversen):

```bash
uv run anwb-files save
```

---

## Projectstructuur

```
anwb-files-mcp/
  pyproject.toml
  .python-version
  src/anwb_files_mcp/
    __init__.py
    client.py      # HTML ophalen + __NEXT_DATA__ extraheren
    parser.py      # ruwe payload -> modellen (defensieve padzoeker)
    models.py      # Pydantic-modellen (Road, Segment, Totals, ...)
    errors.py      # FetchError, StructureError
    server.py      # MCP-server + de 5 tools
    cli.py         # standalone CLI (anwb-files)
  tests/
    fixtures/filelijst.html   # offline snapshot
    test_*.py
```

## Eenheid & velden

| Bronveld | Betekenis | Normalisatie in output |
| --- | --- | --- |
| `delay` | Vertraging in **seconden** | `delayMinutes` (afgerond op 0,1) |
| `distance` | Lengte in **meters** | `distanceM` + `distanceKm` |
| `category` | `jams`, `road-closed`, `roadworks`, `radars` | ongewijzigd |
| `incidentType` | `slow-traffic`, `queing-traffic`, `stationary-traffic`, `road-closed`, `roadworks`, `radar`, `unknown` | ongewijzigd |
| `reason` / `events[].text` | Nederlandse beschrijving | ongewijzigd |
| `coordinates` / `loc` | Punt (lat/lon) | `location` in output |
| `HM` | Hectometerpaal (alleen bij flitsers) | `hm` |

De bron bevat **geen** eigen bijwerkt-timestamp; `fetchedAt` in de output is het
moment van ophalen door deze server.

## Licentie

MIT — zie [LICENSE](LICENSE). De onderliggende verkeersdata is © ANWB / TomTom.
