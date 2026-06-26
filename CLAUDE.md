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
