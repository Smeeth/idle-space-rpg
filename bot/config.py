"""Configuration for the Idle Space RPG Bot."""

import os
from dataclasses import dataclass, field


@dataclass
class IRCConfig:
    """IRC connection settings."""

    server: str = os.getenv("IRC_SERVER", "irc.baerenbude.org")
    port: int = int(os.getenv("IRC_PORT", "6697"))
    use_tls: bool = os.getenv("IRC_TLS", "true").lower() == "true"
    nickname: str = os.getenv("BOT_NICK", "StationAI")
    realname: str = os.getenv("BOT_REALNAME", "Idle Space RPG - Station AI")
    channel: str = os.getenv("IRC_CHANNEL", "#idle-space-rpg")
    nickserv_pass: str = os.getenv("NICKSERV_PASS", "")


@dataclass
class GameConfig:
    """Game mechanics settings."""

    # Base time-to-level in seconds (10 minutes for level 1)
    base_ttl: int = int(os.getenv("BASE_TTL", "600"))
    # Exponential growth factor per level
    level_exponent: float = float(os.getenv("LEVEL_EXPONENT", "1.16"))
    # Tick interval in seconds (how often the game loop runs)
    tick_interval: int = int(os.getenv("TICK_INTERVAL", "5"))
    # Penalty multipliers
    penalty_nick: int = 30
    penalty_part: int = 200
    penalty_quit: int = 20
    penalty_kick: int = 250
    penalty_msg_multiplier: int = 1  # per character
    # Event probabilities (per tick, adjusted)
    event_calamity_chance: float = 0.0002
    event_blessing_chance: float = 0.0002
    event_encounter_chance: float = 0.0003
    event_quest_chance: float = 0.00005


@dataclass
class DatabaseConfig:
    """Database settings."""

    db_path: str = os.getenv("DB_PATH", "/data/idle_space_rpg.db")


@dataclass
class Config:
    """Main configuration container."""

    irc: IRCConfig = field(default_factory=IRCConfig)
    game: GameConfig = field(default_factory=GameConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
