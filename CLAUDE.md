# Working method

This repo's documentation was deleted on purpose. There is no domain spec yet, and there is not
meant to be one until it has been rebuilt from scratch and confirmed by the owner. Until then, follow
these rules without exception.

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
