from enum import Enum


class ScheduleRuleKey(str, Enum):
    """A single, reorderable optimisation rule for the painting auto-scheduler (NA33 under NA49).

    The scheduler proposes a painting sequence by sorting the active orders lexicographically along
    the manager-configured, ordered list of *enabled* rules (highest priority first), with a stable
    final tie-break on insertion order. Each rule is an independent per-order sort key, so the parts
    compose predictably and the priority order is the only thing the manager tunes.
    """

    # Cluster identical colours together (same RAL + producer + paint code adjacent), groups ordered
    # alphabetically by colour identity. Fewer colour changes on the booth.
    COLOUR = "colour"
    # Earlier planned pickup date first (urgency). Orders without a pickup date sort last.
    DEADLINE = "deadline"
    # "Minimalny przerób" → maximise m² painted per day: do the largest single-colour runs first, so
    # the booth spends more time painting and less time being cleaned between colours. The colour group
    # carrying the most m² leads; this also clusters identical colours (a group shares one key).
    CHANGEOVER = "changeover"


# Catalog of every rule the scheduler knows, with operator-facing Polish copy. The default priority
# order (colour → deadline → changeover, all enabled) is the order of this tuple — owner decision
# 2026-06-23. A config row stores the manager's reordered/toggled view of exactly these keys.
SCHEDULE_RULE_CATALOG: tuple[tuple[ScheduleRuleKey, str, str], ...] = (
    (
        ScheduleRuleKey.COLOUR,
        "Grupowanie kolorami",
        "Trzymaj zlecenia o tym samym kolorze obok siebie — mniej zmian koloru na kabinie.",
    ),
    (
        ScheduleRuleKey.DEADLINE,
        "Termin odbioru",
        "Najpierw zlecenia z najwcześniejszym terminem odbioru.",
    ),
    (
        ScheduleRuleKey.CHANGEOVER,
        "Minimalny przerób (m²/dzień)",
        "Najpierw największe runy jednego koloru — kabina maluje więcej m² między myciami.",
    ),
)

SCHEDULE_RULE_LABELS: dict[ScheduleRuleKey, str] = {key: label for key, label, _ in SCHEDULE_RULE_CATALOG}
SCHEDULE_RULE_DESCRIPTIONS: dict[ScheduleRuleKey, str] = {
    key: description for key, _, description in SCHEDULE_RULE_CATALOG
}

# The default, all-enabled priority order applied before a manager ever saves a config.
DEFAULT_RULE_ORDER: tuple[ScheduleRuleKey, ...] = tuple(key for key, _, _ in SCHEDULE_RULE_CATALOG)
