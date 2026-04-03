"""SQLite database layer for player and game state persistence."""

import sqlite3
import time
from pathlib import Path
from typing import Optional


class Database:
    """Manages player data, equipment, and game events in SQLite."""

    def __init__(self, db_path: str):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        """Initialize database schema."""
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS players (
                nick TEXT PRIMARY KEY,
                character_name TEXT NOT NULL,
                crew_role TEXT NOT NULL DEFAULT 'Recruit',
                level INTEGER NOT NULL DEFAULT 1,
                xp_seconds REAL NOT NULL DEFAULT 0,
                ttl_seconds REAL NOT NULL DEFAULT 600,
                alignment TEXT NOT NULL DEFAULT 'neutral',
                online INTEGER NOT NULL DEFAULT 0,
                last_login REAL,
                created_at REAL NOT NULL,
                total_idle_seconds REAL NOT NULL DEFAULT 0,
                battles_won INTEGER NOT NULL DEFAULT 0,
                battles_lost INTEGER NOT NULL DEFAULT 0,
                quests_completed INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS equipment (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_nick TEXT NOT NULL,
                slot TEXT NOT NULL,
                item_name TEXT NOT NULL,
                item_level INTEGER NOT NULL DEFAULT 1,
                is_unique INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (player_nick) REFERENCES players(nick),
                UNIQUE(player_nick, slot)
            );

            CREATE TABLE IF NOT EXISTS event_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                event_type TEXT NOT NULL,
                description TEXT NOT NULL,
                players_involved TEXT
            );

            CREATE TABLE IF NOT EXISTS quests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                quest_name TEXT NOT NULL,
                description TEXT NOT NULL,
                started_at REAL NOT NULL,
                ends_at REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                participants TEXT NOT NULL
            );
        """)
        self.conn.commit()

    # -- Player CRUD --

    def register_player(self, nick: str, character_name: str, crew_role: str) -> bool:
        """Register a new player. Returns True if successful."""
        try:
            self.conn.execute(
                "INSERT INTO players (nick, character_name, crew_role, created_at, ttl_seconds) "
                "VALUES (?, ?, ?, ?, ?)",
                (nick, character_name, crew_role, time.time(), 600.0),
            )
            self._init_equipment(nick)
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def _init_equipment(self, nick: str):
        """Give starter equipment to a new player."""
        starter_gear = {
            "neural_implant": ("Basic Neural Link", 1),
            "suit": ("Standard EVA Suit", 1),
            "weapon": ("Maintenance Laser", 1),
            "shield": ("Personal Deflector Mk.I", 1),
            "boots": ("Mag-Boots", 1),
            "gloves": ("Utility Gloves", 1),
            "helm": ("Crew Headset", 1),
            "amulet": ("Station ID Badge", 1),
            "charm": ("Lucky Bolt", 1),
            "ring": ("Comm Ring", 1),
        }
        for slot, (name, level) in starter_gear.items():
            self.conn.execute(
                "INSERT INTO equipment (player_nick, slot, item_name, item_level) "
                "VALUES (?, ?, ?, ?)",
                (nick, slot, name, level),
            )

    def get_player(self, nick: str) -> Optional[dict]:
        """Get player data by nick."""
        row = self.conn.execute("SELECT * FROM players WHERE nick = ?", (nick,)).fetchone()
        return dict(row) if row else None

    def get_online_players(self) -> list[dict]:
        """Get all currently online players."""
        rows = self.conn.execute("SELECT * FROM players WHERE online = 1").fetchall()
        return [dict(r) for r in rows]

    def get_top_players(self, limit: int = 10) -> list[dict]:
        """Get top players by level (descending)."""
        rows = self.conn.execute(
            "SELECT * FROM players ORDER BY level DESC, ttl_seconds ASC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def set_online(self, nick: str, online: bool):
        """Set player online/offline status."""
        self.conn.execute(
            "UPDATE players SET online = ?, last_login = ? WHERE nick = ?",
            (1 if online else 0, time.time(), nick),
        )
        self.conn.commit()

    def update_ttl(self, nick: str, seconds_elapsed: float):
        """Reduce a player's time-to-level by elapsed seconds."""
        self.conn.execute(
            "UPDATE players SET ttl_seconds = MAX(0, ttl_seconds - ?), "
            "total_idle_seconds = total_idle_seconds + ? WHERE nick = ? AND online = 1",
            (seconds_elapsed, seconds_elapsed, nick),
        )
        self.conn.commit()

    def add_penalty(self, nick: str, seconds: float):
        """Add penalty time to player's TTL."""
        self.conn.execute(
            "UPDATE players SET ttl_seconds = ttl_seconds + ? WHERE nick = ?",
            (seconds, nick),
        )
        self.conn.commit()

    def level_up(self, nick: str, new_ttl: float):
        """Level up a player and set their new TTL."""
        self.conn.execute(
            "UPDATE players SET level = level + 1, ttl_seconds = ? WHERE nick = ?",
            (new_ttl, nick),
        )
        self.conn.commit()

    # -- Equipment --

    def get_equipment(self, nick: str) -> list[dict]:
        """Get all equipment for a player."""
        rows = self.conn.execute(
            "SELECT * FROM equipment WHERE player_nick = ? ORDER BY slot", (nick,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_item_sum(self, nick: str) -> int:
        """Get total item level sum for a player."""
        row = self.conn.execute(
            "SELECT COALESCE(SUM(item_level), 0) as total FROM equipment WHERE player_nick = ?",
            (nick,),
        ).fetchone()
        return row["total"]

    def upgrade_item(self, nick: str, slot: str, item_name: str, item_level: int):
        """Replace an item in a slot if the new one is better."""
        self.conn.execute(
            "INSERT OR REPLACE INTO equipment (player_nick, slot, item_name, item_level) "
            "VALUES (?, ?, ?, ?)",
            (nick, slot, item_name, item_level),
        )
        self.conn.commit()

    # -- Events --

    def log_event(self, event_type: str, description: str, players: str = ""):
        """Log a game event."""
        self.conn.execute(
            "INSERT INTO event_log (timestamp, event_type, description, players_involved) "
            "VALUES (?, ?, ?, ?)",
            (time.time(), event_type, description, players),
        )
        self.conn.commit()

    def close(self):
        """Close the database connection."""
        self.conn.close()
