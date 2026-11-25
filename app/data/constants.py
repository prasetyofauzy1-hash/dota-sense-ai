"""Static game constants (heroes, items, abilities) from the bundled OpenDota snapshot,
plus DotaSense's curated rule tables.

The curated tables are design heuristics written for this app, not statistics.
They are labeled as such wherever they are shown.
"""
from __future__ import annotations

from collections.abc import Collection
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
    "disable": "Non-piercing hard disables",
    "targeted_disable": "Unit-targeted lockdown",
    "dispellable": "Basic-dispellable control",
    "piercing_disable": "Debuff-immunity-piercing lockdown",
    "invisibility": "Invisibility",
    "evasion": "Evasion",
    "illusions": "Illusions",
    "summons": "Summons / controlled units",
    "magic_immune_wards": "Magic-immune Serpent Wards",
    "clones": "Linked hero clones",
    "healing": "Strong healing / regen",
    "passive": "Strong passive abilities",
    "mana_shield": "Mana-based durability",
    "dispellable_save": "Dispellable defensive buffs",
    "mobility": "High mobility / escapes",
    "armor_reduction": "Armor reduction",
    "push": "Fast tower push",
    "role_nuke": "Possible spell damage",
    "role_control": "Possible control",
    "role_escape": "Possible escape tools",
    "role_push": "Possible lane pressure",
}

# Curated threat tags for commonly seen heroes (DotaSense heuristics).
CURATED_HERO_THREATS: dict[str, list[str]] = {
    "lion": ["disable", "targeted_disable", "magic_burst"],
    "lina": ["magic_burst", "disable"],
    "zuus": ["magic_burst", "targeted_disable"],
    "skywrath_mage": ["magic_burst", "dispellable", "targeted_disable"],
    "leshrac": ["magic_burst", "disable", "push"],
    "tinker": ["magic_burst"],
    "storm_spirit": ["magic_burst", "mobility", "targeted_disable"],
    "queenofpain": ["magic_burst", "mobility"],
    "puck": ["magic_burst", "dispellable", "mobility"],
    "silencer": ["dispellable", "targeted_disable"],
    "death_prophet": ["dispellable", "push", "healing"],
    "doom_bringer": ["targeted_disable", "piercing_disable"],
    "bane": ["targeted_disable", "piercing_disable"],
    "shadow_shaman": ["disable", "targeted_disable", "magic_immune_wards", "push"],
    "faceless_void": ["piercing_disable", "physical_burst", "mobility"],
    "enigma": ["piercing_disable", "targeted_disable", "summons", "push"],
    "magnataur": ["disable"],
    "tidehunter": ["disable"],
    "earthshaker": ["disable", "magic_burst"],
    "phantom_assassin": ["physical_burst", "evasion", "passive"],
    "troll_warlord": ["physical_burst", "dispellable"],
    "juggernaut": ["physical_burst", "healing"],
    "sven": ["physical_burst", "disable", "targeted_disable"],
    "ursa": ["physical_burst"],
    "slark": ["physical_burst", "mobility", "healing"],
    "monkey_king": ["physical_burst", "mobility"],
    "riki": ["invisibility", "physical_burst", "passive"],
    "bounty_hunter": ["invisibility"],
    "clinkz": ["invisibility", "physical_burst"],
    "nyx_assassin": ["invisibility", "magic_burst", "disable"],
    "templar_assassin": ["invisibility", "physical_burst", "armor_reduction"],
    "weaver": ["invisibility", "mobility"],
    "mirana": ["invisibility", "disable"],
    "phantom_lancer": ["illusions", "mobility"],
    "naga_siren": ["illusions", "push", "disable", "targeted_disable"],
    "terrorblade": ["illusions", "physical_burst"],
    "chaos_knight": ["illusions", "physical_burst", "disable", "targeted_disable"],
    "meepo": ["clones", "physical_burst", "dispellable"],
    "broodmother": ["summons", "push", "healing"],
    "furion": ["push", "mobility"],
    "lycan": ["summons", "push"],
    "necrolyte": ["healing", "magic_burst", "targeted_disable", "dispellable_save"],
    "huskar": ["healing", "physical_burst", "passive"],
    "alchemist": ["healing", "disable", "targeted_disable"],
    "morphling": ["physical_burst", "mobility", "targeted_disable"],
    "dazzle": ["healing"],
    "omniknight": ["healing"],
    "oracle": ["healing", "targeted_disable"],
    "witch_doctor": ["healing", "disable", "targeted_disable", "magic_burst"],
    "bristleback": ["passive"],
    "spectre": ["passive", "illusions"],
    "pudge": ["targeted_disable", "piercing_disable", "magic_burst"],
    "axe": ["piercing_disable", "passive"],
    "legion_commander": ["targeted_disable", "piercing_disable", "physical_burst"],
    "slardar": ["armor_reduction", "disable"],
    "dragon_knight": ["armor_reduction", "push", "disable", "targeted_disable"],
    "antimage": ["mobility", "physical_burst", "targeted_disable"],
    "medusa": ["mana_shield", "physical_burst"],
    "tiny": ["disable", "physical_burst"],
    "invoker": ["magic_burst", "disable", "targeted_disable"],
    "viper": ["targeted_disable", "piercing_disable", "passive"],
    "shredder": ["passive", "mobility"],
    "pugna": ["dispellable_save", "magic_burst", "push"],
    "chen": ["healing", "summons", "push"],
    "abaddon": ["healing"],
}

# Map OpenDota roles -> threat tags, used when a hero is not curated.
ROLE_THREATS = {
    "Nuker": "role_nuke",
    "Disabler": "role_control",
    "Escape": "role_escape",
    "Pusher": "role_push",
}

# Cover distinct mechanics before showing more options for the same threat.
COUNTER_FOCUS = (
    "invisibility", "evasion", "passive", "piercing_disable", "targeted_disable",
    "healing", "mana_shield", "dispellable_save", "clones", "illusions", "summons", "magic_immune_wards",
    "dispellable",
)

# Counter items per threat (DotaSense heuristics). Each entry: item key, short why, defensive?
COUNTER_ITEMS: dict[str, list[tuple[str, str, bool]]] = {
    "magic_burst": [
        ("black_king_bar", "Debuff immunity and bonus magic resistance help against non-piercing spells.", True),
        ("pipe", "Team-wide magic barrier absorbs spell damage.", True),
        ("eternal_shroud", "Personal magic resistance against repeated spell damage.", True),
        ("glimmer_cape", "A magic damage barrier and invisibility can save an ally.", True),
    ],
    "disable": [
        ("black_king_bar", "Activate before non-piercing stuns; it does not prevent piercing lockdown.", True),
        ("aeon_disk", "Can protect briefly against follow-up burst if it triggers.", True),
    ],
    "targeted_disable": [
        ("sphere", "Blocks one applicable unit-targeted cast, not area spells; other spells can pop it first.", True),
        ("lotus_orb", "Echo Shell reflects applicable targeted spells but does not block the original.", True),
    ],
    "dispellable": [
        ("manta", "Self basic dispel clears many silences and roots, not hard stuns or persistent zones.", True),
        ("cyclone", "Self-cyclone applies a basic dispel and briefly takes you out of the fight.", True),
        ("lotus_orb", "Basic dispel on cast can clear applicable debuffs from you or an ally.", True),
        ("black_king_bar", "Activation applies a basic dispel, even if the spell itself pierces debuff immunity.", True),
    ],
    "piercing_disable": [
        ("aeon_disk", "BKB will not prevent this lockdown. Aeon Disk can limit follow-up burst, not guarantee an escape.", True),
    ],
    "physical_burst": [
        ("ghost", "Ethereal form makes you immune to physical attacks for a few seconds.", True),
        ("heavens_halberd", "Disarm stops right-clicks if applied before enemy debuff immunity.", False),
        ("assault", "Armor for you, armor reduction for nearby enemies.", True),
        ("blade_mail", "Returns damage to the attacker.", True),
        ("crimson_guard", "Team-wide physical damage block.", True),
    ],
    "evasion": [
        ("monkey_king_bar", "Pierce procs bypass evasion; non-proc attacks can still miss.", False),
        ("bloodthorn", "The caster's and their units' attacks cannot miss the Soul Rend target while the debuff holds; it can be dispelled.", False),
    ],
    "invisibility": [
        ("dust", "Carry Dust to reveal invisible heroes while fighting in its area.", True),
        ("ward_sentry", "True sight on a location.", True),
        ("gem", "Carried true sight for the whole team (lost on death).", True),
    ],
    "illusions": [
        ("mjollnir", "Chain lightning and Static Charge help clear groups of illusions.", False),
        ("bfury", "Melee cleave helps clear grouped illusions.", False),
        ("crimson_guard", "Damage block against many attackers.", True),
    ],
    "summons": [
        ("crimson_guard", "Team damage block helps against many small physical hits from controlled units.", True),
        ("mjollnir", "Chain Lightning helps clear non-magic-immune summons, not Serpent Wards.", False),
    ],
    "magic_immune_wards": [
        ("crimson_guard", "Team damage block helps allies withstand Serpent Ward attacks.", True),
    ],
    "clones": [
        ("shivas_guard", "Area slow helps keep Meepo clones grouped; focus one exposed clone rather than splitting damage.", True),
    ],
    "healing": [
        ("spirit_vessel", "Charged enemy cast cuts healing and regen while the debuff holds; watch for dispels.", False),
        ("skadi", "Repeated attacks apply healing reduction to the target.", False),
    ],
    "passive": [
        ("silver_edge", "Land the opening hit to Break applicable passives; not every passive can be broken.", False),
    ],
    "mana_shield": [
        ("diffusal_blade", "Attack-based mana burn drains the resource Medusa needs for Mana Shield; consider hero fit.", False),
    ],
    "dispellable_save": [
        ("nullifier", "Repeatedly dispels applicable buffs, including Ghost Shroud, Decrepify and Ghost Scepter; it does not remove every save.", False),
    ],
    "mobility": [
        ("orchid", "Silence stops escape spells.", False),
        ("abyssal_blade", "Overwhelm pierces debuff immunity to lock a target.", False),
        ("sheepstick", "Hex stops escapes.", False),
    ],
    "armor_reduction": [
        ("assault", "Armor aura offsets armor reduction.", True),
        ("solar_crest", "A physical damage barrier can protect an ally against focused attacks.", True),
    ],
    "push": [
        ("travel_boots", "More flexible teleports can get you to lanes under pressure.", True),
        ("crimson_guard", "Helps hold high ground against pushes.", True),
    ],
}

# Core item build templates per primary attribute / attack type (DotaSense heuristics).
ATTR_LABELS = {
    "agi": "Agility",
    "str": "Strength",
    "int": "Intelligence",
    "all": "Universal",
}

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

# Plain-English item benefits for newer players (DotaSense heuristics).
ITEM_BENEFITS: dict[str, str] = {
    "magic_wand": "Stores charges when nearby enemies cast spells — activate for an instant burst of HP and mana.",
    "wraith_band": "Cheap early stats (Agility, armor, attack speed) to win lane trades and last-hit.",
    "bracer": "Cheap early stats (Strength, HP regen, damage) to survive lane harass.",
    "null_talisman": "Cheap early stats (Intelligence, mana regen) to cast spells more often in lane.",
    "power_treads": "Attack speed plus switchable stats (Strength for HP, Agility for damage, Intelligence for mana).",
    "phase_boots": "Bonus armor, attack damage, and a short burst of move speed to chase or escape.",
    "arcane_boots": "Restores mana for you and nearby allies on activation.",
    "tranquil_boots": "High move speed and strong HP regeneration while out of combat.",
    "travel_boots": "Global teleport to allied units or buildings so you can defend lanes and join fights.",
    "maelstrom": "Chain lightning on attacks speeds up farming and clears illusions.",
    "mjollnir": "Fast attack speed plus chain lightning and a lightning shield to clear illusions and magic-vulnerable summons.",
    "bfury": "Melee cleave and HP/mana regen to farm fast and clear groups of illusions.",
    "manta": "Creates two illusions and dispels silences, roots, and slows when activated.",
    "black_king_bar": "Grants debuff immunity and bonus magic resistance; piercing lockdown still works.",
    "sphere": "Automatically blocks one targeted spell every few seconds.",
    "butterfly": "High attack speed, damage, and evasion — strong late-game damage and survivability for Agility carries.",
    "satanic": "Massive lifesteal on activation (plus a basic dispel) to heal back to full HP mid-fight.",
    "skadi": "Heavy all-around stats; your attacks slow enemies and reduce their healing.",
    "blink": "Instant short-range teleport to initiate fights, catch fleeing enemies, or reposition.",
    "sange_and_yasha": "All-around stats, move speed, and status resistance (shorter enemy stuns).",
    "assault": "Aura that gives your team armor and attack speed while reducing nearby enemies' armor.",
    "heart": "Massive max HP and passive health regeneration to stay on the frontline.",
    "abyssal_blade": "Melee bash upgrade with a targeted stun that pierces debuff immunity.",
    "force_staff": "Pushes you or an ally forward — great for escaping danger or saving teammates.",
    "glimmer_cape": "Turns you or an ally invisible with a magic-damage barrier.",
    "ultimate_scepter": "Upgrades your hero's abilities with Aghanim's Scepter.",
    "sheepstick": "Turns an enemy into a harmless critter (Hex), disabling them and stopping escapes.",
    "octarine_core": "Reduces all ability and item cooldowns by 25% and adds HP and mana.",
    "refresher": "Resets the cooldown of all your abilities and items for double-ultimate teamfights.",
    "pipe": "Team-wide magic barrier that absorbs incoming spell damage.",
    "eternal_shroud": "High magic resistance and mana restore when taking spell damage — built for tanky frontliners.",
    "aeon_disk": "Triggers a brief damage-immunity shield and dispel when you drop low, stopping instant-burst combos.",
    "cyclone": "Self-dispel that removes silences and lifts you (or an enemy) into the air for 2.5 seconds.",
    "ghost": "Ethereal form makes you immune to physical attacks for 4 seconds (you cannot attack while active).",
    "heavens_halberd": "Disarms an enemy right-click carry so they cannot attack for several seconds.",
    "blade_mail": "Reflects incoming damage back to attackers — strongest on high-HP frontliners.",
    "crimson_guard": "Team-wide physical damage block active — strongest on tanky frontliners against illusions or summons.",
    "monkey_king_bar": "Pierce procs let some of your attacks bypass evasion.",
    "bloodthorn": "Silences a target and lets the caster and their units hit it without missing while Soul Rend holds.",
    "dust": "Reveals and slows invisible enemies in an area around you.",
    "ward_sentry": "Places True Sight on the ground to spot invisible enemies and enemy wards.",
    "gem": "Carried True Sight aura for your whole team (drops on the ground if you die).",
    "spirit_vessel": "Actively reduces an enemy's healing and regeneration while dealing damage over time.",
    "shivas_guard": "The aura slows enemy attacks; activate to slow and damage nearby enemies.",
    "silver_edge": "Invisibility initiation whose first attack applies Break, disabling enemy passive abilities.",
    "orchid": "Silences an enemy so they cannot cast escape or combo spells, then deals bonus burst damage.",
    "solar_crest": "Grants a shield, armor, and attack speed to you or an ally.",
}

# Alternative item if the main recommendation does not fit.
ALTERNATIVES = {
    "black_king_bar": "sphere",
    "sphere": ("black_king_bar", "aeon_disk"),
    "pipe": ("eternal_shroud", "glimmer_cape"),
    "eternal_shroud": ("pipe", "black_king_bar", "glimmer_cape"),
    "glimmer_cape": ("force_staff", "aeon_disk"),
    "manta": ("sange_and_yasha", "cyclone", "black_king_bar"),
    "cyclone": ("manta", "force_staff"),
    "aeon_disk": "sphere",
    "ghost": ("glimmer_cape", "blade_mail", "sphere"),
    "heavens_halberd": ("crimson_guard", "shivas_guard", "ghost"),
    "assault": "shivas_guard",
    "blade_mail": ("crimson_guard", "shivas_guard", "ghost"),
    "crimson_guard": ("blade_mail", "shivas_guard"),
    "monkey_king_bar": "bloodthorn",
    "bloodthorn": "monkey_king_bar",
    "dust": "ward_sentry",
    "ward_sentry": "gem",
    "gem": "dust",
    "mjollnir": ("bfury", "gungir"),
    "bfury": "mjollnir",
    "spirit_vessel": "skadi",
    "shivas_guard": ("skadi", "spirit_vessel"),
    "skadi": ("satanic", "spirit_vessel"),
    "silver_edge": "black_king_bar",
    "orchid": "sheepstick",
    "abyssal_blade": "sheepstick",
    "sheepstick": ("abyssal_blade", "orchid"),
    "solar_crest": ("assault", "glimmer_cape"),
    "travel_boots": ("blink", "crimson_guard"),
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


def alternatives(item: str, counter_tags: Collection[str] = ()) -> tuple[str, ...]:
    """Alternatives for an item, in order of preference."""
    if item == "mjollnir" and "summons" in counter_tags:
        return ("bfury", "maelstrom")
    alt = ALTERNATIVES.get(item)
    return (alt,) if isinstance(alt, str) else tuple(alt or ())

# Items built from these components count as "already covered".
UPGRADES = {
    "diffusal_blade": ["disperser"],
    "orchid": ["bloodthorn"],
    "maelstrom": ["mjollnir", "gungir"],
    "ward_sentry": ["gem"],
    "boots": ["power_treads", "phase_boots", "arcane_boots", "tranquil_boots", "travel_boots"],
    "invis_sword": ["silver_edge"],
    "cyclone": ["wind_waker"],
    "basher": ["abyssal_blade"],
    "hood_of_defiance": ["pipe", "eternal_shroud"],
}
