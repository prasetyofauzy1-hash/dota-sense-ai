"""Domain models shared by providers, engines and the UI."""
from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class DataSource(str, Enum):
    MOCK = "mock"
    LIVE_GSI = "live_gsi"
    NONE = "none"


class GamePhase(str, Enum):
    PRE_GAME = "pre_game"
    LANING = "laning"  # 0-12 min
    MID = "mid"  # 12-30 min
    LATE = "late"  # 30+ min


class Priority(str, Enum):
    HIGH = "high"
    SITUATIONAL = "situational"
    LOW = "low"


class Ability(BaseModel):
    name: str
    level: int = 0
    cooldown: float | None = None
    can_cast: bool | None = None
    ultimate: bool = False


class HeroState(BaseModel):
    name: str | None = None  # internal name, e.g. npc_dota_hero_juggernaut
    hero_id: int | None = None
    level: int | None = None
    health_percent: int | None = None
    mana_percent: int | None = None
    alive: bool | None = None


class GameState(BaseModel):
    """Snapshot of what the player can legitimately see. Unknown fields stay None."""

    source: DataSource = DataSource.NONE
    is_mock: bool = False
    scenario_name: str | None = None
    match_id: str | None = None
    match_active: bool = False
    game_state: str | None = None
    game_time: int | None = None  # seconds, from horn
    is_daytime: bool | None = None
    team: str | None = None  # radiant / dire
    gold: int | None = None
    gpm: int | None = None
    xpm: int | None = None
    kills: int | None = None
    deaths: int | None = None
    assists: int | None = None
    last_hits: int | None = None
    hero: HeroState = Field(default_factory=HeroState)
    items: list[str] = Field(default_factory=list)  # item keys, e.g. "power_treads"
    abilities: list[Ability] = Field(default_factory=list)
    # Enemy heroes are only what the player can see (picks screen / scoreboard).
    # GSI does not expose them to players, so they come from user input or mock data.
    enemy_heroes: list[str] = Field(default_factory=list)
    ally_heroes: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)

    @property
    def phase(self) -> GamePhase:
        if self.game_time is None or self.game_time < 0:
            return GamePhase.PRE_GAME
        minutes = self.game_time / 60
        if minutes < 12:
            return GamePhase.LANING
        if minutes < 30:
            return GamePhase.MID
        return GamePhase.LATE


class ItemRecommendation(BaseModel):
    item: str
    item_name: str
    cost: int | None
    priority: Priority
    reason: str
    benefit: str
    alternative: str | None = None
    alternative_name: str | None = None
    remaining_gold: int | None = None
    score: float = 0.0
    affordable: bool | None = None


class Threat(BaseModel):
    hero: str
    hero_name: str
    tags: list[str]
    severity: float
    explanation: str
    tags_source: str  # "curated" or "roles"


class CounterItem(BaseModel):
    item: str
    item_name: str
    counters: list[str]
    against_heroes: list[str]
    explanation: str
    defensive: bool


class Suggestion(BaseModel):
    category: str
    text: str
    confidence: str  # "high" | "medium" | "low (uncertain)"
    reasons: list[str] = Field(default_factory=list)
