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

  > **Modelling decision (confirmed by owner 2026-06-17):** physically there is a separate decoral
  > packing station after the decoral coat, but the **system intentionally does not track it as its own
  > stage**. The current model — a single trailing `DECORAL_PRODUCTION` stage after `PACKING`, with no
  > separate decoral-packing stage — is accepted as-is. Do **not** add a decoral-packing stage/tab.

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

**Cardinality and dominance (confirmed by owner 2026-06-23):**

- There is **exactly one manual painting station and exactly one automatic spray booth** — so there
  are **two parallel painting resources, one per method**. This is why the planning model has exactly
  two line sequences (Automat / Ręczna): it mirrors two physical machines, not a stylistic choice.
- The **automatic line carries the large majority** of the factory's throughput, cost, and profit.
  The **colour-changeover cost is highest on the automatic booth**, so the automatic sequence is the
  primary thing worth optimising (colour grouping matters most there).

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

- **Surface preparation** and **packing** are shared by both production methods. Surface preparation
  is a **cleaning/preparation wash** before painting — a multi-step process with washing, an acid step,
  and several rinses; the exact chemistry is **not tracked by the system** and is low priority to
  document (owner, 2026-06-17). It is also where the **real received quantity is counted** (see §3).
  Surface preparation is a **plan-driven feeder** (not driven by physical arrival of parts) and
  **stays ahead of painting** — it is not the bottleneck (owner, 2026-06-23). Historically the order
  came from the manager's printed planning sheet.
  Because these two stages are **single shared resources** feeding/draining the two parallel painting
  lines, their order is **not** the per-line painting queue position (that number is only meaningful
  within one line). It is **derived** (N49-10): surface preparation interleaves the two lines, feeding
  next the line with the **smaller prepared-but-not-yet-painted buffer** (the line closest to starving
  its booth; ties → automatic), buffer measured in **pieces**; packing follows **physical readiness** +
  the packing-slot reservation, with **no position numbering**. See the scheduling model in
  `WORKFLOW.md` → "Target planning model" and item NA49 in `IMMEDIATE_NEXT_ACTIONS.md`.
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
- **Real counted quantity is the operational truth.** Surface preparation counts the **actual
  received** pieces, which can differ from the ordered quantity (see *incomplete on arrival* below).
  From that point on, the **real counted quantity — not the ordered quantity — is what downstream
  stations and packing validate against** (packing checks "did anything go missing?" against the real
  count, and it works). ⚠️ **Known UI gap (owner, 2026-06-17):** most screens still *display* the
  ordered quantity rather than the real counted one — logged as **NA26** for NA25 verification/fix.
- **Incomplete on arrival.** A work order is *incomplete on arrival* when **fewer elements physically
  arrive than were ordered**. Such an order **may still go to production** — it is not blocked — and the
  surface-preparation count becomes the operational quantity. The marker is office state and does not
  change the production workflow.
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

- **Total production** = the m² (or pieces) of each order, counted **once** ("how much product passed
  through the factory").
- It partitions cleanly along **either** axis, and **both partitions sum to the same total**:
  - **By production method:** `manual + automatic = total` (every order has exactly one method).
  - **By order coating type:** `RAL-only + decoral = total`. ⚠️ The "RAL" bucket here means
    **orders whose coating type is RAL only** (no decoral) — *not* "everything that received a RAL
    coat." A decoral order physically gets a RAL base coat too, but as a **product** it is classified
    `DECORAL` and counts **once, on the decoral side**. Label this bucket "czysty RAL / RAL only", never
    just "RAL", or it reads as "all RAL coats" and the partition stops summing (this exact mislabel
    caused real confusion — owner, 2026-06-17).
- Therefore the method split and the coating split are **two independent ways of cutting the same
  whole**, not a single three-way bucket. **"Manual + automatic + decoral" is NOT a valid sum** —
  manual + automatic already equals the whole; decoral lives on the other axis, so adding it
  double-counts every decoral order. (This was the owner's original phrasing; it was retracted once we
  worked a numeric example.)
- **Counting *coats applied* is a different question** that deliberately does **not** sum to total
  product: every order gets a RAL coat (incl. decoral orders' base), and decoral orders get an extra
  decoral coat, so "RAL coats + decoral coats" > total product. That is line/coat workload (see the
  "przejazd decoral" counter below), not throughput.

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

---

## 5. Additional work-order types and markers

### Ocynk (galvanizing)

The factory galvanises parts (a zinc anti-corrosion layer). **From the system's perspective an
`is_ocynk` order must behave exactly like a normal order** — same stages, same routing, freely
combined with RAL/decoral and manual/automatic. The only requirement is that the order is **clearly
marked as OCYNK** so stations see it; physical station work differs, but the *system* flow does not.
`is_ocynk` is an independent marker and does not change routing (owner, 2026-06-17).

### Przemalowanka (repaint)

A *przemalowanka* is a job to **repaint elements that already carry a coating** (recolour / refresh
existing parts). System behaviour: it is always a **standalone customer work order** (never a
correction child — modelled as `work_order_kind = PRZEMALOWANKA`), and it **skips
`SURFACE_PREPARATION`**. Apart from skipping surface preparation it behaves like a normal order.
*Why* it skips surface prep was confirmed with a process-knowledgeable colleague but the underlying
physical reason is **[TBD — not captured]**.

---

## 6. Glossary

Short canonical definitions. For *system* semantics (states, validation, READY, corrections) the
authority remains `WORKFLOW.md`; this glossary gives the plain meaning and links the concept to its
home.

| Term (PL) | Meaning |
|---|---|
| **Element / sztuka** | A physical part handled in the factory. Counted in pieces. Not the same as a work order. |
| **Zlecenie (work order)** | A system record tracking one client's ordered work. Has a production method and a coating type (§1). |
| **Profil / Akcesorium** | The two piece categories that partition a work order's `total_quantity` (`profiles + accessories = total` when both known). See `WORKFLOW.md`. |
| **Metoda produkcji** | `MANUAL` (painter sprays by hand) or `AUTOMATIC` (hung on cranes → automatic spray booth). One of the two axes (§1). |
| **Powłoka / Coating** | `RAL` (one RAL-colour powder coat) or `DECORAL`. The other axis (§1). |
| **RAL** | A single powder coat in a specified RAL colour; the order finishes at packing. |
| **Decoral** | A RAL base coat **plus one additional decorative coat** applied at the separate Decoral station after base-coat packing (§1). |
| **Przejazd Decoral (decoral pass)** | The work event of applying the decoral coat. A **line-workload** counter (overlaps the base coat); never part of total throughput (§4.1). |
| **Ocynk** | Galvanizing marker (`is_ocynk`). System-neutral: behaves like a normal order, just flagged (§5). |
| **Przemalowanka** | Repaint of already-coated parts; standalone order that skips surface preparation (§5). |
| **Przygotowanie powierzchni (surface preparation)** | The cleaning/prep wash before painting; also where the real received quantity is counted (§2, §3). |
| **Poprawka (correction)** | Pieces that fail QC at packing and are reworked. RAL → in-place `CORRECTION` batch; DECORAL → child "P" order. See `WORKFLOW.md`. |
| **Niekompletne na przyjęciu (incomplete on arrival)** | Fewer elements arrived than ordered; the order may still go to production (§3). |
| **Ilość zamówiona / declared (`total_quantity`)** | What the client ordered. |
| **Ilość policzona / actual received** | Real pieces counted at surface preparation — the **operational truth** downstream (§3). |
| **READY** | The order is fully complete (exact rule: `WORKFLOW.md` "READY Rules"). |
| **`process_status`** | Backend-derived display status; never a stored column (see `WORKFLOW.md` / `CLAUDE.md`). |

---

## 7. Planning ground truth — daily norm, capacity, changeover & line choice

> Confirmed by the owner + a process-knowledgeable colleague in a clean-slate process interview
> (2026-06-23). This is the physical grounding for the planning model in `docs/WORKFLOW.md`
> ("Target planning model") and the build plan in `IMMEDIATE_NEXT_ACTIONS.md` (NA49). Items still
> awaiting the colleague are flagged.

### The daily norm is a FLOOR, not a ceiling

The factory is profitable only **above a minimum daily throughput** (electricity, wages, materials pay
off). The norm is that minimum, not a target to stop at:

- **≥ 800 m²** on a long day (shift 07:00–21:00, ~14 h).
- **≥ 500 m²** on a short day (shift 07:00–15:00, ~8 h).

These are **floors to clear**, not capacity. The physical **ceiling** is higher: the automatic booth
runs at **~60–100 m²/h**, so a long day can physically reach ~1000–1400 m². A day is *bad* when it falls
**below** the floor (too little product), not when it is busy. The optimisation target = clear the floor
every working day and pack **toward the ceiling** (more product = more profit), in deadline order, with
minimal changeover loss. **Shift length follows the available work**: enough ready work to clear ≥ 800 →
run a long day; only ~500 worth → run a short day (a long day would idle below 800 = unprofitable).

### The automatic booth is the constraint; manual is unmeasured overflow

- Automatic carries the large majority of throughput; **~60–100 m²/h**, measurable.
- **Manual-line throughput and manual paint consumption are not measurable** in practice — manual is a
  fuzzy **overflow valve**, not precisely planned or metered.
- Surface preparation is *slightly* slower than painting but **usually keeps up**, so the booth rarely
  waits on it (a buffer of cleaned parts exists; its size is **not important**). Prep is a plan-driven
  feeder, **not a bottleneck** — do not over-model it. The main exception is the paint-surprise case
  below.

### Colour-changeover economics (the main optimisation dial)

A colour change on the automatic booth costs time, scaled by the **100 m² threshold** (the same number
as the paint-demand threshold):

- next order **< 100 m²** → "bez odzysku" (no powder recovery) → change **≤ 15 min**.
- next order **> 100 m²** → "z odzysku" (powder recovered, fuller clean) → change **up to 30 min**.

Cost also depends on **colour direction/similarity**: going from a **lighter** colour to a **darker** one
is cheap (residue of the lighter colour is invisible in the darker one — owner's example: white → grey),
while **dark → light** needs a full clean (residue would show). So the cheap day shape is a single
**light → dark sweep**; a dark → light reset is the expensive event to minimise. Grouping identical
colours into runs (zero changeover) is the first lever; ordering the remaining changes light → dark is
the second. **Colour lightness is derivable from the RAL code**, so the system can compute this.
The exact minutes/frequency are not tracked by people — the system should **learn them from production
data** (see §4) — but the grouping reward is large. The **15/30-min bands are confirmed**; the *frequency*
of colour changes is **not a fixed number** — it depends on the day's order mix, so the system learns it.
The RAL-lightness light→dark model is the working assumption (owner's white→grey example); the owner could
not confirm whether colour "families" override it — ⚠️ *still to confirm with the colleague.* **Built
(N49-5/6):** the within-day sweep + the size+direction changeover cost are implemented; RAL→lightness
lives in **one documented helper** `app/manager/colour.py::ral_lightness` (a coarse group/anchor map, NOT
a perceptual L\* scale) — that helper is the **single point to revisit** when this open question is
answered (a CIE-Lab/HLC mapping or a family table would replace it there, nowhere else).

### Line choice (manual vs automatic) is a real planning lever

Every order *can* run on either line; the part does not force it. Rule of thumb (owner): an order goes to
**manual** when it is **small in m² AND its colour repeats nowhere else** on the order list (no group to
join); otherwise it goes to **automatic** so it can join a colour run. Line choice therefore interacts
with colour grouping and with load-balancing idle stations.

### Decoral is not a second bottleneck

The decoral second coat is purely **aesthetic** ("to make it look nicer"); **changing the foil costs no
time**, and the decoral station does not clog the line. Decoral is ~1/4 of orders. It is a trailing
appended stage, **not** something the scheduler must separately optimise.

### Deadlines are HARD

Each order's **planned pickup date ("Termin odbioru", `planned_pickup_date`) is a hard deadline** — it is
**always agreed and entered at order creation**, and the order must ship by it. Hardness hierarchy for
planning: **hard deadline > daily floor (strong economic target) > colour grouping (optimisation).** A
small day carrying a hard deadline runs even below the floor (must ship), as an explicit exception.
The deadline **horizon is comfortable — "definitely not for tomorrow"** (owner, 2026-06-23), so the
planner has **real freedom to reorder for colour grouping** within the hard-deadline constraint; a tight
deadline is the exception, not the rule. (Exact typical slack still worth confirming with the colleague.)

### Measurement signals available (no booth tap)

Operators do **not** tap the booth itself. The automatic line emits, per order, a **HANGING start**
(tapped — hanging claims the line resource) and a **PACKING completion**, both in the append-only
`StageTransitionEvent` log. These **bracket the whole automatic pass** (hang + booth + oven + packing).
So aggregate throughput (m²/h) and — statistically, over many orders — colour-changeover cost are
**learnable from existing signals**; pure booth time is not isolated, and that is accepted.
