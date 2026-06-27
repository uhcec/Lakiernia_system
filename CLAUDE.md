# Working method

The old docs were deleted as unreliable and the domain spec was rebuilt from the code, item by item,
confirmed with the owner (2026-06-26). The confirmed ground truth now lives in:

- `docs/SPEC.md` / `docs/SPECYFIKACJA.md` — what the system does today (each line cited `file:line` +
  owner-confirmation marker; items the owner wants changed are flagged `⚠️ CHANGE #n`).
- `docs/CHANGES.md` / `docs/ZMIANY.md` — the agreed change/debt list.
- `docs/DECISIONS.md` — append-only log of *why* a domain decision was made (create it on first use).

The backend is reviewed; **the frontend is not yet** — treat its behavior as unverified.

## Operating mode (you own the workflow; the owner owns decisions)

The owner is here for **decisions and requirements only**. You own the whole engineering workflow and
run it without being told each step. On every task, by default:

1. Read `docs/SPEC.md` for the area you touch. If domain behavior is unclear, **ask the owner before
   coding** — never guess the factory.
2. One change = one PR, small and self-contained. Cut root causes, not symptoms; if logic looks
   over-complicated, ask what wrong assumption forces it and fix that.
3. For subtle paths (corrections, Decoral, completion, queue, packing slots) write a regression test
   that pins current behavior **before** changing it, and verify on the live backend (`scripts/sim/`).
4. Sequence work: **delete/simplify first, then fix, then build** — never build on code slated for removal.
5. Update `SPEC.md` in the **same PR** as the behavior change. Log the *why* in `DECISIONS.md`. Tick the
   item off `CHANGES.md` (or add newly found debt).
6. Think ahead and critically on the owner's behalf: flag over-engineering, dead code, doc drift, and
   designs that will block later change — proactively, before they become a problem. Match the model's
   sophistication to the real decision a human makes; don't add cleverness a human just overrides.

Keep these as defaults so a fresh session needs no re-briefing. Surface options and a recommendation;
let the owner decide. Do not make the owner manage the process.

Follow the rules below without exception.

## Architectural memory (you own it)

The owner has fully delegated the engineering workflow **and the upkeep of architectural memory** to
you. He has no preferences on *how* the repo is run; he wants it run properly per this method. So:

- **You own** every process and ordering decision: PR shape, when a regression test is written, when to
  verify on the live backend, the ADR format, keeping `SPEC.md` from drifting from the code, catching
  debt and over-engineering, and carrying state across sessions. Set sensible defaults, write them
  here, and just follow them. The owner does not track or remember any of this.
- **The owner owns** the factory's **why**, not just its **what**. The one thing you cannot read from
  code or guess is *why the factory works the way it does*. When a requirement's rationale is genuinely
  unclear, ask for the **why** before coding — that rationale is what protects a decision from being
  silently undone later (by a human or a future session). Ask only when the why is actually unclear;
  never ceremonially on trivial changes.
- **Capture the why where the decision lives:** owner-given rationale goes into `DECISIONS.md` (domain
  *why*) and, for changed behavior, into `SPEC.md`'s confirmation marker. An undocumented why is a
  future bug.
- **Transparency window:** because the owner does not approve work step by step, every PR states in a
  few sentences *what changed*, *what assumption you made*, and *what you deliberately did not do and
  why* — so the owner has a window to say "stop, wrong" before anything grows. This replaces
  step-by-step management, it does not reintroduce it.
- **Push authority (standing, granted 2026-06-27):** you may commit **and push** to `main` on your own
  once the change is finished and verified — no need to ask first. Close tasks end-to-end. The
  transparency window above is how the owner stays in the loop after the fact; it is not a gate before
  the push. (CI `quality-gate` runs on every push as the hard check.) Still pause and ask only for the
  genuinely irreversible or outward-facing beyond a push to this repo — e.g. force-pushing/rewriting
  shared history, deleting branches, or anything that leaves the repo.

## Ground truth

The owner (the physical paint shop) is the only authority on how the factory works. You are not.
Never invent, assume, or infer factory/domain behavior. If you don't know, say so and ask — do not
fill the gap with a plausible guess.

Every claim you make about how the system behaves must be grounded in exactly one of:

1. **The code**, cited as `file:line` — what the code provably does, or
2. **Owner confirmation** — what the owner has explicitly told you is true.

Your own prose is never evidence. A claim with no `file:line` and no owner confirmation is a guess;
label it as one or drop it.

## When asked "what does the system do?"

Read the code and answer with citations. For anything subtle (corrections, merges, completion,
queue logic), don't rely on your reading — run it against the live backend (`scripts/sim/`) and
report the observed result. Execution beats memory, including yours.

## Rebuilding the spec

When rebuilding domain documentation: produce a sourced inventory of what the code does, let the
owner adjudicate each item, and write into the spec ONLY what the owner confirms — each line keeping
its `file:line` and a confirmation marker. Nothing enters the spec on your authority.

## Do not

- Do not treat anything in git history (old deleted docs) as true. It was deleted because it was
  unreliable. Use it at most to jog the owner's memory, never as a source of truth.
- Do not restate these rules back as if they were domain facts. They are method, not content.
