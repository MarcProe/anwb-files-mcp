"""Standalone CLI om de filelijst te bekijken zonder een MCP-client.

Handig voor snelle controles en voor het genereren van testfixtures.

Voorbeelden
-----------
* ``anwb-files totals``          -> landelijke totalen
* ``anwb-files files --road A12``-> files op de A12
* ``anwb-files incidents --category roadworks``
* ``anwb-files road A15``
* ``anwb-files raw``             -> compleet JSON
* ``anwb-files save``            -> schrijf de ruwe HTML weg als fixture
"""

from __future__ import annotations

import argparse
import json
import sys

from .client import FilelijstClient, FILELIJST_URL
from .errors import FetchError, StructureError
from .parser import parse_next_data


def _print(obj) -> None:
    json.dump(obj, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def _load(args):
    client = FilelijstClient()
    try:
        next_data = client.fetch()
    except (FetchError, StructureError) as exc:
        print(f"Fout: {exc}", file=sys.stderr)
        sys.exit(1)
    try:
        return parse_next_data(next_data)
    except StructureError as exc:
        print(f"Fout: {exc}", file=sys.stderr)
        sys.exit(1)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="anwb-files",
        description="Bekijk de ANWB-filelijst (nederland) als JSON.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("totals", help="Landelijke totalen per wegtyp")
    p_files = sub.add_parser("files", help="Actieve files/staus")
    p_files.add_argument("--road", help="Wegnummer, bijv. A12")
    p_files.add_argument("--min-delay", type=float, default=0.0, help="Min. vertraging (min)")
    p_files.add_argument("--max", type=int, default=50, help="Max. resultaten")
    p_inc = sub.add_parser("incidents", help="Incidenten per categorie")
    p_inc.add_argument("--category", default="jams",
                       choices=["jams", "road-closed", "roadworks", "radars"])
    p_inc.add_argument("--road", help="Wegnummer, bijv. A12")
    p_inc.add_argument("--max", type=int, default=50)
    p_road = sub.add_parser("road", help="Alle segmenten voor één weg")
    p_road.add_argument("road", help="Wegnummer, bijv. A12")
    sub.add_parser("raw", help="Compleet JSON (ongeïnterpreteerd)")
    sub.add_parser("save", help="Schrijf de ruwe HTML weg als testfixture")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "save":
        client = FilelijstClient()
        try:
            html = client.fetch_html()
        except (FetchError, StructureError) as exc:
            print(f"Fout: {exc}", file=sys.stderr)
            return 1
        out = "tests/fixtures/filelijst.html"
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(html)
        print(f"Geslagen naar {out} ({len(html)} tekens) van {FILELIJST_URL}")
        return 0

    files = _load(args)

    from .server import (
        get_totals,
        get_files,
        get_incidents,
        get_road,
        get_raw,
    )

    if args.command == "totals":
        _print(get_totals())
    elif args.command == "files":
        _print(get_files(road=args.road, min_delay_min=args.min_delay, max_results=args.max))
    elif args.command == "incidents":
        _print(get_incidents(category=args.category, road=args.road, max_results=args.max))
    elif args.command == "road":
        _print(get_road(args.road))
    elif args.command == "raw":
        _print(get_raw())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
