from enum import Enum


class ScheduleRuleKey(str, Enum):
    """A single, reorderable optimisation rule for the painting auto-scheduler (NA33 under NA49).

    The scheduler proposes a painting sequence by sorting the active orders lexicographically along
    the manager-configured, ordered list of *enabled* rules (highest priority first), with a stable
    final tie-break on insertion order. Each rule is an independent per-order sort key, so the parts
    compose predictably and the priority order is the only thing the manager tunes.
    """

    # Earlier planned pickup date first (urgency). Orders without a pickup date sort last.
    DEADLINE = "deadline"
    # Cluster identical colours together (same RAL + producer + paint code adjacent), groups ordered
    # alphabetically by colour identity. Fewer colour changes on the booth.
    COLOUR = "colour"


# Catalog of every rule the scheduler knows, with operator-facing Polish copy. The default priority
# order (deadline → colour, all enabled) is the order of this tuple — owner decision 2026-06-26
# (CHANGES #6: two rules only; the "maksymalny przerób"/max-throughput rule was dropped). A config row
# stores the manager's reordered/toggled view of exactly these keys.
SCHEDULE_RULE_CATALOG: tuple[tuple[ScheduleRuleKey, str, str], ...] = (
    (
        ScheduleRuleKey.DEADLINE,
        "Termin odbioru",
        "Najpierw zlecenia z najwcześniejszym terminem odbioru.",
    ),
    (
        ScheduleRuleKey.COLOUR,
        "Grupowanie kolorami",
        "Trzymaj zlecenia o tym samym kolorze obok siebie — mniej zmian koloru na kabinie.",
    ),
)

SCHEDULE_RULE_LABELS: dict[ScheduleRuleKey, str] = {key: label for key, label, _ in SCHEDULE_RULE_CATALOG}
SCHEDULE_RULE_DESCRIPTIONS: dict[ScheduleRuleKey, str] = {
    key: description for key, _, description in SCHEDULE_RULE_CATALOG
}

# The default, all-enabled priority order applied before a manager ever saves a config.
DEFAULT_RULE_ORDER: tuple[ScheduleRuleKey, ...] = tuple(key for key, _, _ in SCHEDULE_RULE_CATALOG)
