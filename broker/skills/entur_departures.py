#!/usr/bin/env python3
"""Entur departure lookups — broker-only, allowlisted stops, read-only."""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Tuple

TOOL_NAME = "entur-departures"

ENTUR_GRAPHQL_URL = "https://api.entur.io/journey-planner/v3/graphql"

ALLOWED_STOPS: Dict[str, Dict[str, str]] = {
    "jernbanetorget": {"id": "NSR:StopPlace:58366", "name": "Jernbanetorget"},
    "nationaltheatret": {"id": "NSR:StopPlace:58404", "name": "Nationaltheatret"},
    "oslo-s": {"id": "NSR:StopPlace:59872", "name": "Oslo S"},
}

_ALIAS_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
_MAX_DEPARTURES = 10


def _client_name() -> str:
    return os.environ.get("ENTUR_CLIENT_NAME", "subro-agent-broker")


def _departures_query(stop_id: str, count: int) -> str:
    return (
        "{ stopPlace(id: "
        + json.dumps(stop_id)
        + ") { name estimatedCalls(numberOfDepartures: "
        + str(count)
        + ") { expectedDepartureTime destinationDisplay { frontText } "
        "serviceJourney { journeyPattern { line { publicCode transportMode } } } } } }"
    )


def _fetch_departures(stop_id: str, count: int) -> Dict[str, Any]:
    payload = json.dumps({"query": _departures_query(stop_id, count)}).encode("utf-8")
    req = urllib.request.Request(
        ENTUR_GRAPHQL_URL,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "ET-Client-Name": _client_name(),
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _format_departures(data: Dict[str, Any], alias: str, stop_meta: Dict[str, str]) -> str:
    if data.get("errors"):
        return json.dumps({"ok": False, "errors": data["errors"]}, indent=2)

    stop = (data.get("data") or {}).get("stopPlace")
    if not stop:
        return json.dumps(
            {"ok": False, "error": "stopPlace not found in response", "alias": alias},
            indent=2,
        )

    departures: List[Dict[str, Any]] = []
    for call in stop.get("estimatedCalls") or []:
        line = (
            (call.get("serviceJourney") or {})
            .get("journeyPattern", {})
            .get("line", {})
        )
        departures.append(
            {
                "time": call.get("expectedDepartureTime"),
                "destination": (call.get("destinationDisplay") or {}).get("frontText"),
                "line": line.get("publicCode"),
                "mode": line.get("transportMode"),
            }
        )

    return json.dumps(
        {
            "ok": True,
            "alias": alias,
            "stop": stop.get("name") or stop_meta["name"],
            "stop_id": stop_meta["id"],
            "departures": departures,
        },
        indent=2,
        ensure_ascii=False,
    ) + "\n"


def run(args: List[str]) -> Tuple[int, str, str, List[str]]:
    if not args or args[0] in ("-h", "--help"):
        aliases = ", ".join(sorted(ALLOWED_STOPS))
        return (
            0,
            (
                f"Usage: {TOOL_NAME} <stop-alias> [count]\n"
                f"Allowed stops: {aliases}\n"
                f"Max departures: {_MAX_DEPARTURES}\n"
            ),
            "",
            [],
        )

    alias = args[0].lower()
    if not _ALIAS_RE.match(alias):
        return 2, "", f"invalid stop alias: {args[0]!r}\n", []

    if alias not in ALLOWED_STOPS:
        allowed = ", ".join(sorted(ALLOWED_STOPS))
        return 2, "", f"stop not allowed: {alias!r} (allowed: {allowed})\n", []

    count = 5
    if len(args) >= 2:
        try:
            count = int(args[1])
        except ValueError:
            return 2, "", f"invalid count: {args[1]!r}\n", []
    if count < 1 or count > _MAX_DEPARTURES:
        return 2, "", f"count must be 1..{_MAX_DEPARTURES}\n", []

    stop_meta = ALLOWED_STOPS[alias]
    try:
        data = _fetch_departures(stop_meta["id"], count)
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        return 1, "", f"Entur HTTP {e.code}: {err_body}\n", []
    except urllib.error.URLError as e:
        return 1, "", f"Entur request failed: {e.reason}\n", []
    except Exception as e:
        return 1, "", f"Entur request failed: {e}\n", []

    return 0, _format_departures(data, alias, stop_meta), "", []
