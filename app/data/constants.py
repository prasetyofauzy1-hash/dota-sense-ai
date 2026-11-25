"""Static game constants (heroes, items, abilities) from the bundled OpenDota snapshot,
plus DotaSense's curated rule tables.

The curated tables are design heuristics written for this app, not statistics.
They are labeled as such wherever they are shown.
"""
from __future__ import annotations

from functools import lru_cache

from app.data.opendota import _load_snapshot

HERO_PREFIX = "npc_dota_hero_"


@lru_cache(maxsize=1)
def heroes() -> dict[int, dict]:
    return {int(k): v for k, v in _load_snapshot("heroes").items()}


@lru_cache(maxsize=1)
def heroes_by_name() -> dict[str, dict]:
    """Keyed by short name, e.g. 'juggernaut'."""
    return {h["name"].removeprefix(HERO_PREFIX): h for h in heroes().values()}


@lru_cache(maxsize=1)
def items() -> dict[str, dict]:
    return _load_snapshot("items")


@lru_cache(maxsize=1)
def items_by_id() -> dict[int, str]:
    return {v["id"]: k for k, v in items().items()}


def hero_short(name: str | None) -> str | None:
    if not name:
        return None
    return name.removeprefix(HERO_PREFIX)


def hero_display(name: str | None) -> str:
    short = hero_short(name)
    if not short:
        return "Unknown"
    hero = heroes_by_name().get(short)
    return hero["localized_name"] if hero else short.replace("_", " ").title()


def item_display(key: str | None) -> str:
    if not key:
        return "—"
    item = items().get(key)
    return item["dname"] if item else key.replace("_", " ").title()


def item_cost(key: str) -> int | None:
    item = items().get(key)
    return item.get("cost") if item else None


# --- Threat tags -------------------------------------------------------------
THREAT_LABELS = {
    "magic_burst": "Magic burst damage",
    "physical_burst": "Physical burst / right-click",
    "disable": "Hard disables / stuns",
    "silence": "Silences",
    "invisibility": "Invisibility",
    "evasion": "Evasion",
    "illusions": "Illusions / summons",
    "healing": "Strong healing / regen",
    "passive": "Strong passive abilities",
    "mobility": "High mobility / escapes",
    "armor_reduction": "Armor reduction",
    "push": "Fast tower push",
}

# Curated threat tags for commonly seen heroes (DotaSense heuristics).
CURATED_HERO_THREATS: dict[str, list[str]] = {
    "lion": ["disable", "magic_burst"],
    "lina": ["magic_burst", "disable"],
    "zuus": ["magic_burst"],
    "skywrath_mage": ["magic_burst", "silence"],
    "leshrac": ["magic_burst", "push"],
    "tinker": ["magic_burst", "push"],
    "storm_spirit": ["magic_burst", "mobility"],
    "queenofpain": ["magic_burst", "mobility"],
    "puck": ["magic_burst", "silence", "mobility"],
    "silencer": ["silence"],
    "death_prophet": ["silence", "push", "magic_burst"],
    "doom_bringer": ["disable", "silence"],
    "bane": ["disable"],
    "shadow_shaman": ["disable", "push"],
    "faceless_void": ["disable", "physical_burst", "evasion"],
    "enigma": ["disable", "illusions"],
    "magnataur": ["disable"],
    "tidehunter": ["disable"],
    "earthshaker": ["disable", "magic_burst"],
    "phantom_assassin": ["physical_burst", "evasion"],
    "troll_warlord": ["physical_burst", "evasion"],
    "juggernaut": ["physical_burst", "healing"],
    "sven": ["physical_burst", "disable"],
    "ursa": ["physical_burst"],
    "slark": ["physical_burst", "mobility", "healing"],
    "monkey_king": ["physical_burst", "mobility"],
    "riki": ["invisibility", "physical_burst"],
    "bounty_hunter": ["invisibility"],
    "clinkz": ["invisibility", "physical_burst"],
    "nyx_assassin": ["invisibility", "magic_burst", "disable"],
    "templar_assassin": ["invisibility", "physical_burst", "armor_reduction"],
    "weaver": ["invisibility", "mobility"],
    "mirana": ["invisibility", "disable"],
    "phantom_lancer": ["illusions", "evasion"],
    "naga_siren": ["illusions", "push", "disable"],
    "terrorblade": ["illusions", "physical_burst"],
    "chaos_knight": ["illusions", "physical_burst", "disable"],
    "meepo": ["illusions", "physical_burst"],
    "broodmother": ["illusions", "push"],
    "furion": ["push", "mobility"],
    "lycan": ["illusions", "push"],
    "necrolyte": ["healing", "magic_burst"],
    "huskar": ["healing", "magic_burst"],
    "alchemist": ["healing", "disable"],
    "morphling": ["healing", "mobility"],
    "dazzle": ["healing"],
    "omniknight": ["healing"],
    "oracle": ["healing"],
    "witch_doctor": ["healing", "disable", "magic_burst"],
    "bristleback": ["passive"],
    "spectre": ["passive", "illusions"],
    "pudge": ["disable", "magic_burst"],
    "axe": ["disable", "passive"],
    "legion_commander": ["disable", "physical_burst"],
    "slardar": ["armor_reduction", "disable"],
    "dragon_knight": ["armor_reduction", "push", "disable"],
    "anti_mage": ["mobility", "passive"],
    "antimage": ["mobility", "passive"],
    "medusa": ["passive"],
    "tiny": ["disable", "physical_burst"],
    "invoker": ["magic_burst", "disable"],
}

# Map OpenDota roles -> threat tags, used when a hero is not curated.
ROLE_THREATS = {
    "Nuker": "magic_burst",
    "Disabler": "disable",
    "Escape": "mobility",
    "Pusher": "push",
    "Carry": "physical_burst",
}

# Counter items per threat (DotaSense heuristics). Each entry: item key, short why, defensive?
COUNTER_ITEMS: dict[str, list[tuple[str, str, bool]]] = {
    "magic_burst": [
        ("black_king_bar", "Spell immunity blocks most magic burst and disables.", True),
        ("pipe", "Team-wide magic barrier absorbs spell damage.", True),
        ("eternal_shroud", "Magic resistance and spell lifesteal for cores.", True),
        ("glimmer_cape", "Magic resistance + invisibility to save an ally.", True),
    ],
    "disable": [
        ("black_king_bar", "Spell immunity prevents most stuns.", True),
        ("sphere", "Blocks one targeted disable every few seconds.", True),
        ("manta", "Dispels some disables and silences.", True),
        ("aeon_disk", "Buys time against burst-and-disable combos.", True),
    ],
    "silence": [
        ("manta", "Basic dispel removes many silences.", True),
        ("black_king_bar", "Spell immunity prevents most silences.", True),
        ("cyclone", "Self-dispel removes silences.", True),
    ],
    "physical_burst": [
        ("ghost", "Ethereal form makes you immune to physical attacks for a few seconds.", True),
        ("heavens_halberd", "Disarm stops a right-click carry.", False),
        ("assault", "Armor for you, armor reduction for nearby enemies.", True),
        ("blade_mail", "Returns damage to the attacker.", True),
        ("crimson_guard", "Team-wide physical damage block.", True),
    ],
    "evasion": [
        ("monkey_king_bar", "True Strike pierces evasion.", False),
        ("bloodthorn", "Silence + True Strike against the target.", False),
    ],
    "invisibility": [
        ("dust", "Reveals invisible heroes in an area.", True),
        ("ward_sentry", "True sight on a location.", True),
        ("gem", "Carried true sight for the whole team (lost on death).", True),
    ],
    "illusions": [
        ("mjollnir", "Chain lightning clears illusions and summons.", False),
        ("bfury", "Cleave damages groups of illusions.", False),
        ("crimson_guard", "Damage block against many attackers.", True),
    ],
    "healing": [
        ("spirit_vessel", "Reduces enemy healing and regen.", False),
        ("shivas_guard", "Aura reduces enemy healing; area slow.", False),
        ("skadi", "Attacks reduce enemy healing.", False),
    ],
    "passive": [
        ("silver_edge", "Break disables passive abilities.", False),
    ],
    "mobility": [
        ("orchid", "Silence stops escape spells.", False),
        ("abyssal_blade", "Pierces spell immunity to lock a target.", False),
        ("sheepstick", "Hex stops escapes.", False),
    ],
    "armor_reduction": [
        ("assault", "Armor aura offsets armor reduction.", True),
        ("solar_crest", "Bonus armor for you or an ally.", True),
    ],
    "push": [
        ("travel_boots", "Global mobility to defend towers.", True),
        ("crimson_guard", "Helps hold high ground against pushes.", True),
    ],
}

# Core item build templates per primary attribute / attack type (DotaSense heuristics).
CORE_BUILD = {
    "agi": {"laning": ["magic_wand", "wraith_band", "power_treads"],
            "mid": ["maelstrom", "manta", "black_king_bar"],
            "late": ["butterfly", "satanic", "skadi"]},
    "str": {"laning": ["magic_wand", "bracer", "phase_boots"],
            "mid": ["blink", "black_king_bar", "sange_and_yasha"],
            "late": ["assault", "heart", "abyssal_blade"]},
    "int": {"laning": ["magic_wand", "null_talisman", "arcane_boots"],
            "mid": ["force_staff", "glimmer_cape", "ultimate_scepter"],
            "late": ["sheepstick", "octarine_core", "refresher"]},
    "all": {"laning": ["magic_wand", "bracer", "phase_boots"],
            "mid": ["blink", "black_king_bar", "ultimate_scepter"],
            "late": ["assault", "sheepstick", "refresher"]},
}

# Alternative item if the main recommendation does not fit.
ALTERNATIVES = {
    "black_king_bar": "sphere",
    "sphere": "black_king_bar",
    "pipe": "eternal_shroud",
    "eternal_shroud": "pipe",
    "glimmer_cape": "force_staff",
    "manta": "cyclone",
    "cyclone": "manta",
    "aeon_disk": "sphere",
    "ghost": "blade_mail",
    "heavens_halberd": "ghost",
    "assault": "shivas_guard",
    "blade_mail": "crimson_guard",
    "crimson_guard": "blade_mail",
    "monkey_king_bar": "bloodthorn",
    "bloodthorn": "monkey_king_bar",
    "dust": "ward_sentry",
    "ward_sentry": "gem",
    "gem": "dust",
    "mjollnir": ("bfury", "gungir"),
    "bfury": "mjollnir",
    "spirit_vessel": "shivas_guard",
    "shivas_guard": "skadi",
    "skadi": "spirit_vessel",
    "silver_edge": "black_king_bar",
    "orchid": "sheepstick",
    "abyssal_blade": "sheepstick",
    "sheepstick": "abyssal_blade",
    "solar_crest": "assault",
    "travel_boots": "crimson_guard",
    "power_treads": "phase_boots",
    "phase_boots": "power_treads",
    "arcane_boots": "tranquil_boots",
    "magic_wand": "bracer",
    "wraith_band": "bracer",
    "bracer": "wraith_band",
    "null_talisman": "bracer",
    "tranquil_boots": "arcane_boots",
    "maelstrom": "desolator",
    "butterfly": "satanic",
    "satanic": "butterfly",
    "blink": "force_staff",
    "force_staff": "glimmer_cape",
    "sange_and_yasha": "manta",
    "heart": "assault",
    "octarine_core": ("ultimate_scepter", "bloodstone"),
    "ultimate_scepter": "octarine_core",
    "refresher": ("sheepstick", "ethereal_blade"),
}


def alternatives(item: str) -> tuple[str, ...]:
    """Alternatives for an item, in order of preference."""
    alt = ALTERNATIVES.get(item)
    return (alt,) if isinstance(alt, str) else tuple(alt or ())

# Items built from these components count as "already covered".
UPGRADES = {
    "orchid": ["bloodthorn"],
    "maelstrom": ["mjollnir", "gungir"],
    "ward_sentry": ["gem"],
    "boots": ["power_treads", "phase_boots", "arcane_boots", "tranquil_boots", "travel_boots"],
    "invis_sword": ["silver_edge"],
    "cyclone": ["wind_waker"],
    "basher": ["abyssal_blade"],
    "hood_of_defiance": ["pipe", "eternal_shroud"],
}
