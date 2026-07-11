# GO_LIVE — burn-down to production at the shop

Created 2026-07-09 (owner's call: finish Lakiernia first, then it re-enters
his outreach as a live reference). **"Finished" means deployed and in daily
use at the shop — not "no ideas left."** This file is the single burn-down
list; tick items here, log domain decisions in `DECISIONS.md` as usual.

Scope note: all 11 items in `CHANGES.md` from the 2026-06-26 pass are closed
and both layers have had a sourced review pass (`SPEC.md`, `FRONTEND_TRIAGE.md`).
**Amended 2026-07-11:** an independent execution-first review
(`docs/INDEPENDENT_REVIEW_2026-07-11.md`) found verified pre-live bugs —
registered as `CHANGES.md` #12–#17 and listed in section 1a below — so the
remaining work is bug fixes **plus** verification, deployment, and real-use
confirmation.

## 0. Owner decisions needed before engineering starts

- [ ] **D1 — Where does production run?** Options: (a) a machine on the
      shop LAN — the frontend dev config was already written with shop-LAN
      use in mind (see the host note in `scripts/dev.sh`); (b) hosted on
      the VPS with TLS + remote access from the shop; (c) other.
      Recommendation: pick by the shop's internet reliability — tablets on
      the floor should not stop working when the uplink does. Decide with
      the co-author.
- [ ] **D2 — Target go-live date** and who enters the initial data
      (clients, paints/stock, employees) — owner, co-author, or prepared
      as a seed.
- [ ] **D3 — C3/C4 frontend dedup: pre-live or post-live?** It is "the one
      medium-weight item left" (`FRONTEND_TRIAGE.md`) but is pure internal
      hygiene with no user-visible behavior. Recommendation: **defer to
      post-live** — a refactor of the three stage pages right before
      deployment adds regression risk for zero shop-visible gain.
- [ ] **D4 — Real user list**: who gets accounts, which roles/stations,
      initial passwords, and which tablets/devices log in where. Include the
      session policy: the 12h JWT expiry vs. shift-shared tablets (an expiry
      mid-count currently discards the operator's input — `CHANGES.md` #16d).
- [ ] **D5 — Undercount presentation** (blocks `CHANGES.md` #12): when fewer
      pieces arrive than ordered (prep counts 3 of 5), should the order be
      redefined to the counted amount with an audit trail of the original,
      or stay at the ordered total with a visible shortfall? The 2026-06-30
      decision confirmed the *intent* (count is ground truth, order
      completes); the code implements neither presentation today.
- [ ] **D6 — QC card format** (blocks `CHANGES.md` #17): is the
      Excel-formatted quality-control card required as-is, or is a printable
      page / plain xlsx download acceptable? The current implementation only
      works on a Windows host with Excel installed — this couples to D1.

## 1a. Pre-live bug fixes (2026-07-11 independent review — `CHANGES.md` #12–#17)

Blocking before cutover — each produces a state the office cannot repair, on
a path a real shop day will hit:

- [ ] **#12 + #13** — undercount completion never finalizes (queue slot never
      released, "Gotowe" at 3/5) and the poisoned slot then 500s the
      manager's planning. Fix together; needs D5 first.
- [ ] **#14** — a DONE stage can restart while downstream is active,
      rewriting the counted quantity; add the guard + an office-only
      administrative reset.
- [ ] **#15** — office list silently caps at 50 orders; wire pagination.

Strongly recommended before cutover:

- [ ] **#16** — frontend floor-robustness batch (white-screen `JSON.parse`,
      stale-response guards, Polish network errors, drafts across 401).
- [ ] **#17** — QC document off Windows/Excel COM (per D6; gated on D1).

## 1. Pre-deployment engineering (Claude Code lane)

- [ ] **Fresh confirming sim run** of the live completion+queue path —
      explicitly still open per `REVIEW_LEDGER.md` row 7 (`scripts/sim/`).
- [ ] **Local quality gate green** — mirror CI (`.github/workflows/
      quality-gate.yml`): pytest, `alembic upgrade head && alembic check`,
      `scripts/check_spec_citations.py`, frontend build + tests.
- [ ] **Production configuration** (`app/core/config.py` is env-driven via
      `.env`): set a real `JWT_SECRET` (the committed dev placeholder is
      rejected outside development by design), `APP_ENV=production`,
      `BACKEND_CORS_ORIGINS` for the real frontend origin, `DATABASE_URL`
      pointing at the production SQLite file on durable storage,
      attachments dir likewise. Review `JWT_EXPIRY_MINUTES` (default 12h ≈
      one shift) against real shift patterns.
- [ ] **Production serving**: uvicorn without `--reload` under a systemd
      unit (or the D1 platform's equivalent); frontend production build
      (`npm run build`) served as static files — decide nginx/caddy vs.
      FastAPI static mount. `scripts/dev.sh` is dev-only and must not be
      the production entry point.
- [ ] **Network/access hardening per D1**: LAN → bind to LAN interface +
      firewall; VPS → TLS + no unauthenticated public surface. (The dev
      instance on the VPS stays loopback-only and never holds production
      data.)
- [ ] **Production data backup**: automated backup of the SQLite DB +
      attachments dir with a tested restore, running from day one.

## 2. Data & people readiness

- [ ] Seed real reference data per D2/D4: users (real passwords), clients,
      foils, paints + actual stock (the board flags missing stock as
      "wpisz stan farby" rather than blocking, but starting with real
      numbers makes feasibility statuses meaningful from day one).
- [ ] **Owner walkthrough on the real shop tablet(s)** — several
      `REVIEW_LEDGER.md` rows can only be confirmed by the owner's eyes on
      the running shop (Decoral second-pass badge wording, capacity-board
      shift behavior matching floor reality).
- [ ] Brief the operators: station logins, stage completion, correction
      flows (paint vs. foil checkpoints), the manager's shift-length
      control.

## 3. Cutover

- [ ] Go-live day: real orders enter the system; agree the fallback (paper
      forms as before) if something blocks — no big-bang dependency.
- [ ] Watch the quantity-leak tripwire on early completions
      (`REVIEW_LEDGER.md` row 6): a flagged leak is an upstream-model bug
      to investigate, not noise.

## 4. Post-live — measure, don't just predict

- [ ] Sweep `REVIEW_LEDGER.md` as its triggers fire (7 rows open, last
      swept 2026-06-30): each first real event (completion, correction
      round, auto-schedule, recorded short day, leak) confirms or refutes
      a decision's expected outcome. Move confirmed rows down; a refuted
      row becomes a `CHANGES.md` item.
- [ ] Revisit D3 (C3/C4 dedup) and the consciously-deferred triage items
      once the system has been quiet in production for a while.

## Definition of done (for "Lakiernia is live")

Real orders flowing at the shop, operators using station views, at least
one real completion confirmed clean (`REVIEW_LEDGER.md` row 7), backups
running. At that point the owner's outreach documents may call it "live in
production at a real paint shop" — and not before.
