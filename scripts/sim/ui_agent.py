"""Browser-driving primitive for the black-box UI simulation (the *eyes and hands* of a persona).

A persona agent in this simulation has **zero knowledge** of the codebase: it may only see and click its
own station's page, exactly like a tester dropped onto one screen (see ``TESTER_BRIEF.md``). This module
is the thin mechanical layer that gives a persona those eyes and hands — it owns *nothing* about what the
persona decides.

It drives the real React frontend (Vite dev server) over Chromium via Playwright, logs in through the
actual login form as a station user, and hands back screenshots (vision) + a short list of the clickable
things on the page so the persona can target actions precisely. It deliberately does NOT read the backend
or the repo: if it can't be seen on the page, the persona doesn't know it.

Two long-lived modes let a persona drive across many separate tool calls (each call is its own process):

    serve  --station X [--port 9222]   launch Chromium (CDP open), log in, hold the page open (run in bg)
    act    --port 9222 <verb> [args]   connect over CDP, do ONE action on the open page, re-screenshot

    # verbs:  look | click "<text>" | fill "<field>" "<value>" | press "<key>" | scroll up|down
    # every act writes ui_runs/<station>.png and prints a clickable-element summary

Plus the Phase-0 one-shot proof:

    (default __main__)  --station X     log in once and screenshot (no persistent session)

Dev-only. Assumes the Vite dev server (default :5173) and backend (:8000) are already running.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import Page, sync_playwright

# Seeded dev credentials (mirrors scripts/sim_client.CREDENTIALS) and the station panel each login lands
# on after auth (frontend App.tsx routes). Keep in sync with both. Full-access logins (biuro, kierownik)
# land on /zlecenia; kierownik's own panel is /kierownik, reached by navigation.
STATIONS: dict[str, tuple[str, str]] = {
    "biuro": ("bi1", "/zlecenia"),
    "kierownik": ("ki1", "/zlecenia"),
    "przygotowanie": ("prz1", "/przygotowanie"),
    "zawieszanie": ("zaw1", "/zawieszanie"),
    "produkcja-reczna": ("rec1", "/produkcja-reczna"),
    "produkcja-automat": ("aut1", "/produkcja-automat"),
    "pakowanie": ("pak1", "/pakowanie"),
    "decoral": ("dec1", "/produkcja-decoral"),
}

# Frontend the personas drive. Defaults to the owner's dev server (:5173); the isolated full run
# overrides this to the sim Vite (:5174) which proxies to the sim backend (:8001) — see vite.sim.config.ts.
BASE_URL = os.environ.get("SIM_FRONTEND_URL", "http://127.0.0.1:5173")
_SHOTS_DIR = Path(__file__).resolve().parent / "ui_runs"


def login(page: Page, station: str, *, base_url: str = BASE_URL) -> str:
    """Log in through the real login form as ``station``; return the landed path. Raises on mismatch."""
    if station not in STATIONS:
        raise SystemExit(f"unknown station '{station}'. Known: {', '.join(STATIONS)}")
    password, expected_path = STATIONS[station]
    page.goto(f"{base_url}/login", wait_until="networkidle")
    page.get_by_placeholder("np. zawieszanie").fill(station)
    page.get_by_placeholder("••••").fill(password)
    page.get_by_role("button", name="Zaloguj się").click()
    page.wait_for_url(f"**{expected_path}", timeout=10_000)
    page.wait_for_load_state("networkidle")
    return expected_path


def shoot(page: Page, label: str) -> Path:
    """Viewport screenshot — what the operator sees *above the fold* — into ui_runs/.

    Deliberately NOT full_page: a full-page capture of a long panel is a huge image and every step
    keeps it in the persona's context, which dominates token cost. Viewport-only keeps each image
    small; the persona uses the `scroll` verb to see below the fold when it needs to."""
    _SHOTS_DIR.mkdir(parents=True, exist_ok=True)
    path = _SHOTS_DIR / f"{label}.png"
    page.screenshot(path=str(path), full_page=False)
    return path


def clickables(page: Page) -> str:
    """A short text inventory of what a persona can act on: buttons, links, inputs. Helps it aim clicks
    without knowing the DOM — it still *decides* from the screenshot; this just makes targeting reliable."""
    lines: list[str] = []
    try:
        buttons = [b.strip() for b in page.get_by_role("button").all_inner_texts() if b.strip()]
        if buttons:
            lines.append("buttons: " + " | ".join(dict.fromkeys(buttons)))
        links = [a.strip() for a in page.get_by_role("link").all_inner_texts() if a.strip()]
        if links:
            lines.append("links: " + " | ".join(dict.fromkeys(links)))
        fields = []
        for inp in page.locator("input, textarea").all():
            ph = inp.get_attribute("placeholder") or ""
            if ph.strip():
                fields.append(ph.strip())
        if fields:
            lines.append("input fields (by placeholder): " + " | ".join(dict.fromkeys(fields)))
    except Exception as exc:  # noqa: BLE001 — inventory is best-effort, never fatal
        lines.append(f"(could not enumerate elements: {exc})")
    return "\n".join(lines) if lines else "(no obvious buttons/links/inputs found)"


# --- persistent-session modes (CDP) --------------------------------------------------------------

def _cdp_url(port: int) -> str:
    return f"http://127.0.0.1:{port}"


def serve(station: str, port: int) -> int:
    """Launch Chromium with a CDP port, log in as ``station``, and hold the page open forever.

    Run this in the background. ``act`` then connects over CDP to drive the same live page."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=[f"--remote-debugging-port={port}"])
        page = browser.new_context(viewport={"width": 1366, "height": 900}).new_page()
        landed = login(page, station)
        # kierownik is full-access and lands on /zlecenia, but its real workspace is the planning panel.
        if station == "kierownik":
            page.goto(f"{BASE_URL}/kierownik", wait_until="networkidle")
            landed = "/kierownik"
        shoot(page, station)
        print(f"SERVE station={station} port={port} landed={landed} (holding session open)", flush=True)
        try:
            while True:
                time.sleep(3600)
        finally:
            browser.close()
    return 0


def _open_page(pw, port: int) -> Page:
    browser = pw.chromium.connect_over_cdp(_cdp_url(port))
    context = browser.contexts[0]
    return context.pages[0]


def act(port: int, station: str, verb: str, args: list[str]) -> int:
    """Connect to the live session, perform ONE action, re-screenshot, print result + clickables."""
    with sync_playwright() as pw:
        page = _open_page(pw, port)
        result = "ok"
        try:
            if verb == "look":
                pass
            elif verb == "reload":
                page.reload(wait_until="networkidle")
                result = "reloaded page"
            elif verb == "click":
                target = args[0]
                btn = page.get_by_role("button", name=target, exact=False)
                if btn.count() > 0:
                    btn.first.click()
                else:
                    page.get_by_text(target, exact=False).first.click()
                result = f"clicked '{target}'"
            elif verb == "fill":
                field, value = args[0], args[1]
                loc = page.get_by_placeholder(field, exact=False)
                if loc.count() == 0:
                    loc = page.get_by_label(field, exact=False)
                loc.first.fill(value)
                result = f"filled '{field}' = '{value}'"
            elif verb == "press":
                page.keyboard.press(args[0])
                result = f"pressed '{args[0]}'"
            elif verb == "scroll":
                direction = args[0] if args else "down"
                dy = 700 if direction == "down" else -700
                page.mouse.wheel(0, dy)
                result = f"scrolled {direction}"
            else:
                result = f"unknown verb '{verb}'"
            page.wait_for_timeout(800)  # let the UI settle / any request resolve
        except Exception as exc:  # noqa: BLE001 — a failed action IS data; report, don't crash
            result = f"ACTION FAILED: {type(exc).__name__}: {str(exc).splitlines()[0]}"
        shot = shoot(page, station)
        print(json.dumps({
            "result": result,
            "url": page.url,
            "screenshot": str(shot),
            "clickable": clickables(page),
        }, ensure_ascii=False, indent=2))
    return 0


def _phase0(station: str, *, headed: bool) -> int:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=not headed)
        page = browser.new_context(viewport={"width": 1366, "height": 900}).new_page()
        try:
            landed = login(page, station)
            shot = shoot(page, f"phase0_{station}")
            print(f"OK  logged in as '{station}' -> landed on {landed}")
            print(f"OK  screenshot: {shot}")
            return 0
        finally:
            browser.close()


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(description="UI driver for the black-box simulation.")
    sub = parser.add_subparsers(dest="command")

    p_serve = sub.add_parser("serve", help="launch + log in + hold the session open (run in background)")
    p_serve.add_argument("--station", required=True)
    p_serve.add_argument("--port", type=int, default=9222)

    p_act = sub.add_parser("act", help="do one action on a live session and re-screenshot")
    p_act.add_argument("--port", type=int, default=9222)
    p_act.add_argument("--station", required=True, help="used only to name the screenshot file")
    p_act.add_argument("verb", choices=["look", "reload", "click", "fill", "press", "scroll"])
    p_act.add_argument("args", nargs="*")

    # default (no subcommand) = phase-0 one-shot proof
    parser.add_argument("--station", default="przygotowanie", help="(phase-0 mode) station login")
    parser.add_argument("--headed", action="store_true", help="(phase-0 mode) show the browser window")

    args = parser.parse_args(argv)
    if args.command == "serve":
        return serve(args.station, args.port)
    if args.command == "act":
        return act(args.port, args.station, args.verb, args.args)
    return _phase0(args.station, headed=args.headed)


if __name__ == "__main__":
    raise SystemExit(main())
