"""Guard against the recurring "new feature → 'nie udało się…'" class of bug.

In dev the React app talks to the backend through Vite's proxy (frontend/vite.config.ts). The proxy is
an allowlist of top-level path prefixes; a backend router whose prefix is missing is NOT proxied, so the
browser receives Vite's HTML 404 instead of JSON and every call to that endpoint fails with a generic
error (this is exactly what happened to ``/foils``). This test fails whenever a backend router prefix is
not present in the Vite proxy, so a new endpoint can't silently break in dev again.
"""

from pathlib import Path

from app.main import app

# FastAPI's built-in routes are not proxied (the SPA owns the page; docs are hit directly if at all).
_IGNORED_PREFIXES = {"openapi.json", "docs", "redoc"}

_VITE_CONFIG = Path(__file__).resolve().parents[1] / "frontend" / "vite.config.ts"


def _backend_top_level_prefixes() -> set[str]:
    prefixes: set[str] = set()
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/"):
            continue
        first_segment = path.lstrip("/").split("/", 1)[0]
        if first_segment and first_segment not in _IGNORED_PREFIXES:
            prefixes.add(first_segment)
    return prefixes


def test_vite_proxy_covers_every_backend_prefix() -> None:
    config_text = _VITE_CONFIG.read_text(encoding="utf-8")
    missing = sorted(
        prefix for prefix in _backend_top_level_prefixes() if f'"/{prefix}"' not in config_text
    )
    assert not missing, (
        "These backend router prefixes are not in the Vite dev proxy "
        f"(frontend/vite.config.ts) and will fail in the browser: {missing}"
    )
