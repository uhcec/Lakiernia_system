"""Tiny authenticated HTTP client for the workflow-sim agent.

Drives the running backend as a given station-user without hand-rolling JWT on every call.
Logs in once per login name (token cached in the OS temp dir) and attaches the bearer token.
Uses only the standard library so it works in any dev venv.

Usage:
    # base URL defaults to http://127.0.0.1:8000 (override with SIM_BASE_URL)
    python scripts/sim_client.py --as biuro POST /work-orders '{"customer_name": "...", ...}'
    python scripts/sim_client.py --as kierownik POST /manager/work-orders/12/plan '{"production_type": "AUTOMATIC"}'
    python scripts/sim_client.py --as przygotowanie GET  /process/stages/SURFACE_PREPARATION/work-orders
    python scripts/sim_client.py --as admin GET /work-orders/12

Output: HTTP status line on stderr, response body (pretty JSON when possible) on stdout.
Exit code is 0 for 2xx, 1 otherwise — so shell callers can branch on success.

These are the documented development-only credentials (README "Login" section). Authorization is
derived from the JWT the login returns, NOT from any X-Station-Id header (that header is inert).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

# Development-only seeded accounts (README login table). login -> password.
CREDENTIALS = {
    "biuro": "bi1",                 # OFFICE
    "kierownik": "ki1",             # MANAGER
    "przygotowanie": "prz1",        # SURFACE_PREPARATION
    "zawieszanie": "zaw1",          # HANGING
    "produkcja-reczna": "rec1",     # MANUAL_PRODUCTION
    "produkcja-automat": "aut1",    # AUTOMATIC_PRODUCTION
    "pakowanie": "pak1",            # PACKING
    "decoral": "dec1",              # DECORAL_PRODUCTION
    "admin": "adm1",                # OFFICE + admin
}

BASE_URL = os.environ.get("SIM_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
_TOKEN_CACHE = Path(tempfile.gettempdir()) / "lakiernia_sim_tokens.json"


def _load_cache() -> dict[str, str]:
    try:
        return json.loads(_TOKEN_CACHE.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _save_cache(cache: dict[str, str]) -> None:
    try:
        _TOKEN_CACHE.write_text(json.dumps(cache), "utf-8")
    except OSError:
        pass  # cache is an optimisation; losing it just means re-logging in


def _request(method: str, path: str, token: str | None, body: object | None) -> tuple[int, str]:
    url = BASE_URL + ("/" + path.lstrip("/"))
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method.upper())
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as resp:  # noqa: S310 (local dev only)
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")
    except urllib.error.URLError as exc:
        print(f"ERROR: cannot reach {url}: {exc.reason}", file=sys.stderr)
        print("Is the backend running? Start it with: uvicorn app.main:app", file=sys.stderr)
        raise SystemExit(2)


def _login(login: str) -> str:
    if login not in CREDENTIALS:
        print(f"ERROR: unknown login '{login}'. Known: {', '.join(CREDENTIALS)}", file=sys.stderr)
        raise SystemExit(2)
    status, raw = _request("POST", "/auth/login", None, {"login": login, "password": CREDENTIALS[login]})
    if status != 200:
        print(f"ERROR: login as '{login}' failed ({status}): {raw}", file=sys.stderr)
        raise SystemExit(2)
    return json.loads(raw)["access_token"]


def _token_for(login: str, *, force: bool) -> str:
    cache = _load_cache()
    if not force and login in cache:
        return cache[login]
    token = _login(login)
    cache[login] = token
    _save_cache(cache)
    return token


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Authenticated HTTP client for workflow-sim.")
    parser.add_argument("--as", dest="login", required=True, help="station login (e.g. biuro, kierownik)")
    parser.add_argument("--fresh-login", action="store_true", help="ignore any cached token")
    parser.add_argument("method", help="HTTP method (GET/POST/PATCH/PUT/DELETE)")
    parser.add_argument("path", help="path beginning with / (e.g. /work-orders)")
    parser.add_argument("body", nargs="?", default=None, help="JSON request body (string)")
    args = parser.parse_args(argv)

    body = None
    if args.body:
        try:
            body = json.loads(args.body)
        except ValueError as exc:
            print(f"ERROR: body is not valid JSON: {exc}", file=sys.stderr)
            return 2

    token = _token_for(args.login, force=args.fresh_login)
    status, raw = _request(args.method, args.path, token, body)

    # A cached token can expire; retry once with a fresh login on 401.
    if status == 401 and not args.fresh_login:
        token = _token_for(args.login, force=True)
        status, raw = _request(args.method, args.path, token, body)

    print(f"HTTP {status} {args.method.upper()} {args.path}", file=sys.stderr)
    try:
        print(json.dumps(json.loads(raw), ensure_ascii=False, indent=2))
    except ValueError:
        print(raw)
    return 0 if 200 <= status < 300 else 1


if __name__ == "__main__":
    raise SystemExit(main())
