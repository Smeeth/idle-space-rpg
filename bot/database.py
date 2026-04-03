"""MariaDB database layer for player and game state persistence."""

import time
from typing import Optional

import mariadb


class Database:
    """Manages player data, equipment, and game events in MariaDB."""

    def __init__(self, host: str, port: int, user: str, password: str, database: str):
        self.conn_params = {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "database": database,
            "autocommit": False,
        }
        self.conn: mariadb.connection = None
        self._connect()
        self._create_tables()

    def _connect(self):
        """Establish database connection with retry logic."""
        import time as _time

        max_retries = 30
        for attempt in range(max_retries):
            try:
                self.conn = mariadb.connect(**self.conn_params)
                self.conn.autocommit = False
                return
            except mariadb.Error as e:
                if attempt < max_retries - 1:
                    _time.sleep(2)
                else:
                    raise RuntimeError(
                        f"Could not connect to MariaDB after {max_retries} attempts: {e}"
                    )

    def _ensure_connection(self):
        """Reconnect if the connection was lost."""
        try:
            self.conn.ping()
        except Exception:
            self._connect()

    def _cursor(self):
        """Get a cursor, reconnecting if necessary."""
        self._ensure_connection()
        return self.conn.cursor(dictionary=True)

    def _create_tables(self):
        """Initialize database schema."""
        cur = self._cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS players (
                nick VARCHAR(64) PRIMARY KEY,
                character_name VARCHAR(128) NOT NULL,
                crew_role VARCHAR(32) NOT NULL DEFAULT 'Recruit',
                level INT NOT NULL DEFAULT 1,
                xp_seconds DOUBLE NOT NULL DEFAULT 0,
                ttl_seconds DOUBLE NOT NULL DEFAULT 600,
                alignment VARCHAR(16) NOT NULL DEFAULT 'neutral',
                online TINYINT(1) NOT NULL DEFAULT 0,
                last_login DOUBLE,
                created_at DOUBLE NOT NULL,
                total_idle_seconds DOUBLE NOT NULL DEFAULT 0,
                battles_won INT NOT NULL DEFAULT 0,
                battles_lost INT NOT NULL DEFAULT 0,
                quests_completed INT NOT NULL DEFAULT 0
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS equipment (
                id INT AUTO_INCREMENT PRIMARY KEY,
                player_nick VARCHAR(64) NOT NULL,
                slot VARCHAR(32) NOT NULL,
                item_name VARCHAR(128) NOT NULL,
                item_level INT NOT NULL DEFAULT 1,
                is_unique TINYINT(1) NOT NULL DEFAULT 0,
                FOREIGN KEY (player_nick) REFERENCES players(nick)
                    ON DELETE CASCADE ON UPDATE CASCADE,
                UNIQUE KEY uq_player_slot (player_nick, slot)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS event_log (
                id INT AUTO_INCREMENT PRIMARY KEY,
                timestamp DOUBLE NOT NULL,
                event_type VARCHAR(32) NOT NULL,
                description TEXT NOT NULL,
                players_involved VARCHAR(256),
                INDEX idx_timestamp (timestamp),
                INDEX idx_event_type (event_type)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS quests (
                id INT AUTO_INCREMENT PRIMARY KEY,
                quest_name VARCHAR(128) NOT NULL,
                description TEXT NOT NULL,
                started_at DOUBLE NOT NULL,
                ends_at DOUBLE NOT NULL,
                status VARCHAR(16) NOT NULL DEFAULT 'active',
                participants TEXT NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        """)
        self.conn.commit()
        cur.close()

    # -- Player CRUD --

    def register_player(self, nick: str, character_name: str, crew_role: str) -> bool:
        """Register a new player. Returns True if successful."""
        cur = self._cursor()
        try:
            cur.execute(
                "INSERT INTO players (nick, character_name, crew_role, created_at, ttl_seconds) "
                "VALUES (?, ?, ?, ?, ?)",
                (nick, character_name, crew_role, time.time(), 600.0),
            )
            self._init_equipment(nick, cur)
            self.conn.commit()
            return True
        except mariadb.IntegrityError:
            self.conn.rollback()
            return False
        finally:
            cur.close()

    def _init_equipment(self, nick: str, cur):
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
            cur.execute(
                "INSERT INTO equipment (player_nick, slot, item_name, item_level) "
                "VALUES (?, ?, ?, ?)",
                (nick, slot, name, level),
            )

    def get_player(self, nick: str) -> Optional[dict]:
        """Get player data by nick."""
        cur = self._cursor()
        cur.execute("SELECT * FROM players WHERE nick = ?", (nick,))
        row = cur.fetchone()
        cur.close()
        return row

    def get_online_players(self) -> list[dict]:
        """Get all currently online players."""
        cur = self._cursor()
        cur.execute("SELECT * FROM players WHERE online = 1")
        rows = cur.fetchall()
        cur.close()
        return rows

    def get_top_players(self, limit: int = 10) -> list[dict]:
        """Get top players by level (descending)."""
        cur = self._cursor()
        cur.execute(
            "SELECT * FROM players ORDER BY level DESC, ttl_seconds ASC LIMIT ?",
            (limit,),
        )
        rows = cur.fetchall()
        cur.close()
        return rows

    def set_online(self, nick: str, online: bool):
        """Set player online/offline status."""
        cur = self._cursor()
        cur.execute(
            "UPDATE players SET online = ?, last_login = ? WHERE nick = ?",
            (1 if online else 0, time.time(), nick),
        )
        self.conn.commit()
        cur.close()

    def update_ttl(self, nick: str, seconds_elapsed: float):
        """Reduce a player's time-to-level by elapsed seconds."""
        cur = self._cursor()
        cur.execute(
            "UPDATE players SET ttl_seconds = GREATEST(0, ttl_seconds - ?), "
            "total_idle_seconds = total_idle_seconds + ? WHERE nick = ? AND online = 1",
            (seconds_elapsed, seconds_elapsed, nick),
        )
        self.conn.commit()
        cur.close()

    def add_penalty(self, nick: str, seconds: float):
        """Add penalty time to player's TTL."""
        cur = self._cursor()
        cur.execute(
            "UPDATE players SET ttl_seconds = ttl_seconds + ? WHERE nick = ?",
            (seconds, nick),
        )
        self.conn.commit()
        cur.close()

    def level_up(self, nick: str, new_ttl: float):
        """Level up a player and set their new TTL."""
        cur = self._cursor()
        cur.execute(
            "UPDATE players SET level = level + 1, ttl_seconds = ? WHERE nick = ?",
            (new_ttl, nick),
        )
        self.conn.commit()
        cur.close()

    def update_crew_role(self, nick: str, role: str):
        """Update a player's crew role."""
        cur = self._cursor()
        cur.execute(
            "UPDATE players SET crew_role = ? WHERE nick = ?", (role, nick)
        )
        self.conn.commit()
        cur.close()

    def update_alignment(self, nick: str, alignment: str):
        """Update a player's alignment."""
        cur = self._cursor()
        cur.execute(
            "UPDATE players SET alignment = ? WHERE nick = ?", (alignment, nick)
        )
        self.conn.commit()
        cur.close()

    def set_all_offline(self):
        """Set all players offline (for shutdown)."""
        cur = self._cursor()
        cur.execute("UPDATE players SET online = 0")
        self.conn.commit()
        cur.close()

    # -- Equipment --

    def get_equipment(self, nick: str) -> list[dict]:
        """Get all equipment for a player."""
        cur = self._cursor()
        cur.execute(
            "SELECT * FROM equipment WHERE player_nick = ? ORDER BY slot", (nick,)
        )
        rows = cur.fetchall()
        cur.close()
        return rows

    def get_item_sum(self, nick: str) -> int:
        """Get total item level sum for a player."""
        cur = self._cursor()
        cur.execute(
            "SELECT COALESCE(SUM(item_level), 0) AS total FROM equipment WHERE player_nick = ?",
            (nick,),
        )
        row = cur.fetchone()
        cur.close()
        return row["total"] if row else 0

    def upgrade_item(self, nick: str, slot: str, item_name: str, item_level: int):
        """Replace an item in a slot if the new one is better."""
        cur = self._cursor()
        cur.execute(
            "INSERT INTO equipment (player_nick, slot, item_name, item_level) "
            "VALUES (?, ?, ?, ?) "
            "ON DUPLICATE KEY UPDATE item_name = VALUES(item_name), item_level = VALUES(item_level)",
            (nick, slot, item_name, item_level),
        )
        self.conn.commit()
        cur.close()

    # -- Events --

    def log_event(self, event_type: str, description: str, players: str = ""):
        """Log a game event."""
        cur = self._cursor()
        cur.execute(
            "INSERT INTO event_log (timestamp, event_type, description, players_involved) "
            "VALUES (?, ?, ?, ?)",
            (time.time(), event_type, description, players),
        )
        self.conn.commit()
        cur.close()

    def close(self):
        """Close the database connection."""
        if self.conn:
            try:
                self.conn.close()
            except Exception:
                pass
