# Authorization Design Proposal (NA1)

Status: IMPLEMENTED (2026-06-16). The five decisions below were approved as recommended and the
design was implemented; NA1 is closed in `IMMEDIATE_NEXT_ACTIONS.md` (Done section). This document is
retained as the design record.

Implementation summary:

- `StationContext` now carries `station_id` + `is_admin` from the authenticated user;
  `get_station_context` depends on `get_current_user` (`app/audit/context.py`).
- `ensure_station_allowed`: trusts `None`/`SYSTEM` (internal/seed) callers, bypasses for admins,
  removed the `UNKNOWN` early-allow, and denies anything else not in the allowed set.
- Manager statistics gated to manager/admin (`app/manager/service.py` `_ensure_stats_viewer`, wired in
  `app/manager/router.py`).
- No backend code reads `X-Station-Id` anymore; the frontend sends `Authorization: Bearer` on every
  request via the `frontend/src/main.tsx` interceptor.
- Tests: `tests/conftest.py` authenticates as the station named in `X-Station-Id` (non-admin) or admin
  when absent; added `ensure_station_allowed` unit tests and a statistics-gating API test. Verified:
  backend 352 passed, Alembic clean, frontend 70 passed, build passes.

## Problem

Authentication is enforced (every business router depends on `get_current_user`), but **authorization
is derived from the client-supplied `X-Station-Id` header**, not from the authenticated user:

- `ensure_station_allowed` (`app/audit/context.py`) returns early (allows everything) when the station
  is `UNKNOWN`/`SYSTEM`; a missing header → `UNKNOWN` → full bypass.
- The header is parsed only from the request; the frontend sets it from the **URL path**, not the user.
- The JWT carries the real `station_id` and `is_admin` but no service consults them.

Result: any logged-in user can perform any station's action by setting (or omitting) `X-Station-Id`.

## Current state to work with

- JWT payload: `sub` (login), `station_id`, `is_admin` (`app/auth/service.py`).
- `User` model: `login`, `station_id` (string), `is_admin` (`app/auth/models.py`).
- `StationContext` currently holds only `station_id` and is built from the header
  (`get_station_context`).
- Services authorize via `ensure_station_allowed(station_context, allowed_station_ids=..., action=...)`.
- Tests override `get_current_user` to a single **admin/OFFICE** mock and drive per-station authz
  through the `X-Station-Id` header (`tests/conftest.py`). Many tests assert wrong-station `403`s.
- Seed script and internal callers invoke services with `station_context=None` (→ `SYSTEM`).

## Proposed model

Authorize from the **authenticated user**, not the header.

Role → allowed mutating actions:

| Role (user.station_id / flag) | May mutate |
|---|---|
| `is_admin = true` | everything (bypass) |
| `OFFICE` | work-order intake/update, attachments, completed-order release |
| `MANAGER` | planning, queue/reorder, production-type; view statistics |
| `SURFACE_PREPARATION` | surface-prep stage actions |
| `HANGING` | hanging stage actions |
| `MANUAL_PRODUCTION` | manual production stage actions |
| `AUTOMATIC_PRODUCTION` | automatic paint-consumption entry |
| `PACKING` | packing completion / stage actions |
| `DECORAL_PRODUCTION` | decoral production actions |

Reads (lists/details) stay broadly available to any authenticated user (office and manager already
share broad visibility per `docs/FACTORY_USAGE_NOTES.md`). Only **mutations** are role-gated.
Statistics become manager/admin only (not header/route based).

### Decisions to confirm before coding

1. **Admin bypass** — `is_admin` users may perform any action. (Recommended: yes.)
2. **OFFICE vs MANAGER are distinct for mutations** — office = intake/attachments/release; manager =
   planning/queue/stats; neither does the other's mutations (admin does both). (Recommended: yes,
   matches the factory notes.)
3. **Production accounts are single-station** — a production login's `station_id` fixes which station
   actions it may perform; it cannot act as another station. (Recommended: yes.)
4. **`X-Station-Id` becomes audit-only** — still recorded as "which device", but never grants
   authority; authz always comes from the token. (Recommended: yes. Alternative: require the header to
   equal the user's station, else `403` — more friction, little gain.)
5. **`UNKNOWN` HTTP bypass removed** — every HTTP request now has an authenticated user, so the
   `UNKNOWN`/`SYSTEM` early-allow should no longer apply to HTTP. `SYSTEM` stays for internal/seed
   callers that pass `station_context=None`. (Recommended: yes.)

## Implementation outline (once approved)

1. Extend `StationContext` with the actor's role/`is_admin` (e.g., `station_id` + `is_admin`).
2. Change `get_station_context` to depend on `get_current_user` and build the context from
   `user.station_id` + `user.is_admin`; keep the raw `X-Station-Id` only as an audit field.
3. Update `ensure_station_allowed`: admin bypass; remove the HTTP `UNKNOWN` early-allow; keep `SYSTEM`
   for `station_context=None` (internal/seed) only.
4. Gate statistics on manager/admin.
5. Frontend: confirm API clients send `Authorization: Bearer <token>` on every call (verify; the app
   already logs in and `ProtectedRoute` gates navigation). `X-Station-Id` can remain for audit.
6. Tests: add a fixture/helper to authenticate as an arbitrary station/role (override
   `get_current_user` per test). Convert the existing header-driven wrong-station `403` tests to
   user-driven ones. Expect broad churn in `tests/test_*_api.py`.

## Risks / scope

- Largest risk is test churn: most API tests assume an admin user + header-driven station. They need a
  per-test authenticated identity. Plan to land it as one focused change with the conftest helper first.
- Must not lock out the seed script / internal service calls (they use `station_context=None` →
  `SYSTEM`, which stays allowed).
- Keep this strictly an authorization change; do not alter workflow/quantity/correction semantics.

## Acceptance criteria

- A request authenticated as role X cannot perform another role's mutating action, regardless of any
  `X-Station-Id` header; missing header no longer bypasses anything.
- Statistics require manager/admin.
- Admin can perform any action; production accounts are limited to their station.
- Backend + frontend suites green; audit still records the acting station/device.
