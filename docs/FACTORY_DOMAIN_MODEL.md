# Factory Domain Model — Physical Ground Truth

> **Status: DRAFT, under construction.** This document is being built section by section from a
> structured interview with the factory owner. Sections marked **[TBD — interview pending]** are not
> yet confirmed; do not treat them as truth or implement against them. Confirmed sections are the
> authoritative description of how the physical factory works.

## Purpose and place in the doc hierarchy

This document describes **how the paint shop physically works as a manufacturing process** — the
production methods, the coatings, the physical line, the resources, and what gets measured. It is the
*physical ground truth* that sits **beneath** the system docs:

1. **`FACTORY_DOMAIN_MODEL.md` (this doc)** — physical reality of the factory.
2. `WORKFLOW.md` — how the *software* models that reality (states, quantities, corrections, the
   S01–S12 scenario matrix). When WORKFLOW.md explains a "why", it should trace back here.
3. Implementation (services, read models, frontend) — encodes the model.

When the physical model is ever in question during planning or coding, this is the document to
consult and, if reality differs, to correct first.

---

## 1. The two independent axes

A work order is described by **two independent properties**. They are *not* a single category — they
are separate axes, and a work order has one value on each:

- **Production method** — `MANUAL` or `AUTOMATIC`. *How* the parts are processed on the line.
- **Coating type** — `RAL` or `DECORAL`. *What* finish is applied to the parts.

Because the axes are independent, every work order is exactly one of **four** combinations:

| | RAL | DECORAL |
|---|---|---|
| **MANUAL** | manual order, single RAL coat | manual order, RAL base coat + decoral coat |
| **AUTOMATIC** | automatic order, single RAL coat | automatic order, RAL base coat + decoral coat |

Key consequences (confirmed by the owner):

- A single order **can** be both automatic *and* decoral at the same time — the two axes do not
  exclude each other.
- A plain RAL order is **always** either manual or automatic — production method is never absent.
- Therefore "manual", "automatic", and "decoral" are **not three mutually exclusive buckets**.
  "Manual" and "automatic" partition the *production-method* axis; "RAL" and "decoral" partition the
  *coating* axis. (This is the crux of stats reconciliation — see NA23.)

### Coating axis in detail

- **RAL** — the parts receive **one** powder coat in a specified RAL colour, then move through the
  line to packing. One coat, one finishing event.
- **DECORAL** — the parts receive the **same RAL base coat first** (identical handling to a RAL
  order), and **then one additional coat is applied on top** to produce the decorative finish. So a
  decoral order is "a RAL order plus one more coat." The base coat and the decoral coat cover the
  **same physical parts**, so the area (m²) is identical for both — but they are **two distinct
  finishing events** (different moment, recorded separately). The decoral coat is *additional*, never
  a re-slice of the base coat.
  - *Owner's definition (authoritative):* "decoral coating is a RAL coating that then has one more
    coat applied on top of it."
  - **Where the decoral coat is applied (confirmed):** at a dedicated **Decoral production** station
    that comes **after** the base-coat packing. The parts are *not* packed at that station — the
    decoral coat is applied there, and the decoral flow has its **own, separate packing station** that
    comes *after* the decoral coat. So a decoral order's physical sequence is:
    `… → base-coat packing → decoral production (coat applied) → decoral packing`.
  - **Production method of the decoral pass (confirmed):** it **inherits** the order's production
    method — the decoral pass is not separately chosen as manual/automatic.
  - **Nature/purpose of the second coat:** **[TBD — parked]** — deliberately deferred; to be clarified
    with a knowledgeable colleague. Not needed for the current modelling/stats work.

  > ⚠️ **Possible model/reality gap (to verify, do not "fix" yet):** the system today models the
  > decoral pass as a single trailing `DECORAL_PRODUCTION` stage after `PACKING`, with **no separate
  > decoral-packing stage**. The owner describes a distinct decoral packing station *after* the decoral
  > coat. Confirm whether decoral packing is (a) a real, separately tracked step the system is missing,
  > or (b) physically real but intentionally out of system scope, before changing anything.

### Production axis in detail (confirmed)

Manual and automatic are **two separate physical lines** that can run **in parallel** (at the same
time). They differ in how the paint is applied:

- **AUTOMATIC** — parts are **hung on overhead cranes/conveyors** ("suwnice"), ride into a **spray
  booth that paints them automatically**, then go to packing. The hanging step exists **only** for
  automatic (it is the `HANGING` stage / the exclusive automatic-line resource).
- **MANUAL** — a **painter paints the parts by hand** (in a booth), then they go to packing. There is
  **no hanging step** for manual orders.

**Shared vs. separate resources:**

- **Shared by both methods:** surface preparation (the entry step) and **packing** — both lines feed
  into the same shared packing.
- **Separate per method:** the automatic line (hanging + automatic spray booth) vs. the manual
  painting booth. Because the lines are separate, a manual order and an automatic order can be in
  production simultaneously.

### Curing / baking (out of system scope — confirmed)

Parts are cured in an oven, physically located roughly at the packing area. **The system does not
track the baking process** — it is out of scope and should not be modelled as a stage.

---

## 2. The physical line

A part's physical path depends on both axes. Steps marked **(shared)** are the same physical resource
for manual and automatic; the painting step is where the two methods diverge.

```
                         ┌─────────────────────────────────────┐
                         │  Surface preparation (shared entry)  │
                         └──────────────────┬──────────────────┘
                                            │
                  ┌─────────────────────────┴─────────────────────────┐
                  │                                                     │
          AUTOMATIC method                                      MANUAL method
                  │                                                     │
   ┌──────────────▼───────────────┐                     ┌───────────────▼──────────────┐
   │ Hanging on cranes/conveyors  │                     │  Painter paints by hand       │
   │ → automatic spray booth      │   (separate lines,  │  (no hanging step)            │
   │ (HANGING + automatic line)   │    run in parallel) │                               │
   └──────────────┬───────────────┘                     └───────────────┬──────────────┘
                  │                                                     │
                  └─────────────────────────┬─────────────────────────┘
                                            │
                          ┌─────────────────▼─────────────────┐
                          │       Packing (shared)            │
                          └─────────────────┬─────────────────┘
                                            │
                   ┌────────────────────────┴────────────────────────┐
                   │                                                  │
              RAL coating                                      DECORAL coating
                   │                                                  │
            ┌──────▼──────┐                          ┌────────────────▼────────────────┐
            │  Dispatched │                          │  Decoral production (2nd coat)   │
            │  (done)     │                          │  → decoral's own packing         │
            └─────────────┘                          │    → dispatched                  │
                                                      └──────────────────────────────────┘
```

Notes:

- **Surface preparation** and **packing** are shared by both production methods.
- The **automatic** path adds **hanging** (cranes/conveyors) before the automatic spray booth; the
  **manual** path has a painter applying paint by hand with no hanging.
- The two production lines are physically separate and run **in parallel**.
- For **RAL** the part is finished after packing. For **DECORAL** the part continues to the **Decoral
  production** station for the second coat, then through the **separate decoral packing** (see the
  model/reality gap note in §1).
- **Oven curing** happens physically (around the packing area) but is **not tracked** by the system
  (see §1).

---

## 3. Quantities, pieces, and corrections (physical)

- **Unit:** an order covers a quantity of physical **pieces/elements** and a total **area in m²**
  (`total_area_m2`). m² is the primary metric (see §4).
- **Only the corrections-free part is finished output.** At the relevant packing, any pieces that
  fail and need rework are split off as a **correction**; only the part with no corrections counts as
  produced/done (RAL at packing, decoral at decoral packing — see §4).
- **System modelling of corrections** (RAL = reset the same order with a `CORRECTION` batch; DECORAL
  = spin off a child "P" order; quantity is conserved across the chain) is described in detail in
  `WORKFLOW.md` ("Corrections Behavior", scenario matrix S01–S12). This document does not restate it.
- **Physical rework details** (where a failed part physically goes, whether it is stripped/repainted,
  decoral-specific rework): **[TBD — interview pending]**, low priority — the system behaviour is
  already specified in `WORKFLOW.md`.

---

## 4. Measurement — what is counted, where, and when

**Primary metric: square metres (m²).** m² is what the factory cares about most. **Pieces** are a
secondary metric and should also be countable, but m² leads.

**When an order counts as produced (confirmed):**

- **RAL** — done at **packing**, provided no corrections come out at packing.
- **DECORAL** — done at the **decoral packing** (after the decoral production pass), provided no
  corrections come out there.

In both cases the work is counted at the **final packing for that coating**, and only the part with
**no corrections** counts as finished output.

### 4.1 How decoral counts toward total production (the NA23 resolution)

**A decoral order is ONE product, counted ONCE.** The factory measures "how many m² actually passed
through the factory," and a decoral order's parts are a single physical product — the decoral coat is
*a stage in the middle*, **not** a second unit of output. So a decoral order with 10 m² contributes
**10 m²** to total production, **not** 20.

This is **consistent with how throughput is already computed** (`m2_total` sums each order's
`total_area_m2` exactly once, and the decoral pass is a separate series that is *not* added into the
total). It also makes one thing explicit that the system did not yet expose — a clean **coating
partition** of the total:

- **Total production** = the m² (or pieces) of each order, counted **once**.
- It partitions cleanly along **either** axis, and **both partitions sum to the same total**:
  - **By production method:** `manual + automatic = total` (every order has exactly one method).
  - **By coating:** `RAL + decoral = total` (every order has exactly one coating; a decoral order's
    m² counts once, on the decoral side).
- Therefore the manual/automatic and the RAL/decoral splits are **two independent breakdowns of the
  same whole**, not a single three-way bucket. "Manual + automatic + decoral" is **not** a valid sum
  (it would double-count decoral orders, which are already inside manual/automatic).

**Two different meanings of "decoral m²" — do not conflate:**

1. **Decoral as a product/coating (counts toward total, once):** orders whose coating is `DECORAL`,
   measured once like any product. This is the slice that makes `RAL + decoral = total`.
2. **Decoral pass / "przejazd decoral" (workload, NOT part of total):** the m² processed by the
   *decoral line itself* when applying the second coat (recorded at `DECORAL_PRODUCTION` completion).
   This measures how busy the decoral line was; it **overlaps** the base coat (same parts) and must
   **never** be added into total production. The existing "Przejazd Decoral — m² / dzień" chart is
   this second meaning.

> **Design implication for NA23:** offer the detailed view as the two independent partitions of the
> total (by production method, and by coating), where each partition's parts visibly sum to the
> whole. Keep the "przejazd decoral" workload as its own separate counter, clearly labelled as line
> workload and not part of the total. Confirm presentation with the user before building.
