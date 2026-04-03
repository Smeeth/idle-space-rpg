"""Core game engine – handles leveling, events, combat, and penalties."""

import math
import random
import time
from dataclasses import dataclass

from .config import GameConfig
from .database import Database

# ── Sci-Fi Equipment Slots & Name Generators ──────────────────────────

EQUIPMENT_SLOTS = [
    "neural_implant",
    "suit",
    "weapon",
    "shield",
    "boots",
    "gloves",
    "helm",
    "amulet",
    "charm",
    "ring",
]

ITEM_PREFIXES = {
    "neural_implant": ["Cortex", "Synapse", "Quantum", "Neural", "Psionic"],
    "suit": ["Titanium", "Nano-Weave", "Void", "Plasma-Shielded", "Exo"],
    "weapon": ["Particle", "Ion", "Disruptor", "Railgun", "Phaser"],
    "shield": ["Deflector", "Energy", "Graviton", "Phase", "Ablative"],
    "boots": ["Thruster", "Grav", "Stealth", "Jump-Jet", "Mag-Lock"],
    "gloves": ["Haptic", "Power", "Cryo", "Shock", "Micro-Tool"],
    "helm": ["HUD", "Tactical", "Psi-Amp", "Recon", "Command"],
    "amulet": ["Data Core", "Holo-Key", "Signal", "Beacon", "Cipher"],
    "charm": ["Lucky Circuit", "Star Shard", "Void Fragment", "Nano-Charm", "Relic"],
    "ring": ["Comm", "Holo", "Shield", "Sensor", "Control"],
}

ITEM_SUFFIXES = [
    "Mk.I", "Mk.II", "Mk.III", "Mk.IV", "Mk.V",
    "Alpha", "Beta", "Gamma", "Delta", "Omega",
    "Prime", "Elite", "Proto", "X", "Ultra",
]

CREW_ROLES = [
    "Engineer",
    "Pilot",
    "Medic",
    "Scientist",
    "Security",
    "Comms Officer",
    "Navigator",
    "Mechanic",
]

# ── Sci-Fi Event Flavour ──────────────────────────────────────────────

CALAMITY_MESSAGES = [
    "A solar flare disrupts {nick}'s neural implant! +{pct}% TTL.",
    "Micro-meteorite breach in {nick}'s quarters! +{pct}% TTL.",
    "A rogue AI fragment attacks {nick}'s systems! +{pct}% TTL.",
    "{nick} contracts void sickness from sector anomaly! +{pct}% TTL.",
    "Power surge fries {nick}'s {slot}! Item downgraded by {item_pct}%.",
]

BLESSING_MESSAGES = [
    "{nick} discovers an alien data cache! -{pct}% TTL.",
    "Station AI grants {nick} priority systems access! -{pct}% TTL.",
    "A wormhole echo boosts {nick}'s XP stream! -{pct}% TTL.",
    "{nick}'s {slot} is enhanced by nanobots! +{item_pct}% item level.",
    "Friendly alien traders upgrade {nick}'s gear! +{item_pct}% item level.",
]

BATTLE_WIN_MESSAGES = [
    "{winner} outmaneuvers {loser} in a zero-G duel!",
    "{winner}'s particle beam pierces {loser}'s shields!",
    "{winner} hacks {loser}'s suit systems and disables them!",
    "{winner} wins a tactical skirmish against {loser} in the cargo bay!",
]

BATTLE_LOSE_MESSAGES = [
    "{loser} is defeated by {winner} in a boarding drill.",
    "{loser}'s deflector fails against {winner}'s attack!",
    "{winner} outranks {loser} in combat simulations.",
]

LEVEL_UP_MESSAGES = [
    "{nick} has been promoted to Level {level}! New rank: {role}.",
    "Station Command recognizes {nick} – promoted to Level {level}!",
    "{nick}'s service record updated: Level {level}, Role: {role}.",
]


@dataclass
class GameEvent:
    """Represents a game event to be announced in IRC."""

    event_type: str
    message: str
    affected_players: list[str]


class GameEngine:
    """Core game logic for the Idle Space RPG."""

    def __init__(self, db: Database, config: GameConfig):
        self.db = db
        self.config = config

    # ── TTL Calculation ───────────────────────────────────────────────

    def calculate_ttl(self, level: int) -> float:
        """Calculate time-to-level in seconds for a given level."""
        if level <= 60:
            return self.config.base_ttl * (self.config.level_exponent ** level)
        else:
            ttl_60 = self.config.base_ttl * (self.config.level_exponent ** 60)
            return ttl_60 + (86400 * (level - 60))

    # ── Registration ──────────────────────────────────────────────────

    def register(self, nick: str, character_name: str, crew_role: str = "") -> str:
        """Register a new player. Returns status message."""
        if crew_role and crew_role not in CREW_ROLES:
            return (
                f"Unknown role '{crew_role}'. Available: {', '.join(CREW_ROLES)}"
            )
        if not crew_role:
            crew_role = random.choice(CREW_ROLES)
        success = self.db.register_player(nick, character_name, crew_role)
        if success:
            return (
                f"Welcome aboard, {character_name}! "
                f"You've been assigned as {crew_role} on the station. "
                f"Stay online to accumulate experience. Don't speak – idle!"
            )
        return f"{nick}, you are already registered."

    # ── Tick Processing ───────────────────────────────────────────────

    def process_tick(self, seconds_elapsed: float) -> list[GameEvent]:
        """Process one game tick. Returns events to announce."""
        events: list[GameEvent] = []
        online_players = self.db.get_online_players()

        for player in online_players:
            nick = player["nick"]

            # Reduce TTL
            self.db.update_ttl(nick, seconds_elapsed)

            # Refresh player data
            player = self.db.get_player(nick)
            if not player:
                continue

            # Check level-up
            if player["ttl_seconds"] <= 0:
                events.extend(self._level_up(player))

            # Random events
            events.extend(self._check_random_events(player, online_players))

        return events

    def _level_up(self, player: dict) -> list[GameEvent]:
        """Handle player leveling up."""
        events = []
        nick = player["nick"]
        new_level = player["level"] + 1
        new_ttl = self.calculate_ttl(new_level)

        # Determine new role based on level
        new_role = self._get_role_for_level(new_level)

        self.db.level_up(nick, new_ttl)
        self.db.update_crew_role(nick, new_role)

        msg = random.choice(LEVEL_UP_MESSAGES).format(
            nick=nick, level=new_level, role=new_role
        )
        events.append(GameEvent("level_up", msg, [nick]))

        # Item find on level-up
        item_event = self._find_item(nick, new_level)
        if item_event:
            events.append(item_event)

        # Battle on level-up (25% chance below 25, 100% at 25+)
        if new_level >= 25 or random.random() < 0.25:
            battle = self._trigger_battle(nick, new_level)
            if battle:
                events.append(battle)

        self.db.log_event("level_up", msg, nick)
        return events

    def _get_role_for_level(self, level: int) -> str:
        """Map level ranges to crew roles/ranks."""
        if level < 5:
            return "Recruit"
        elif level < 10:
            return "Crewman"
        elif level < 20:
            return "Ensign"
        elif level < 30:
            return "Lieutenant"
        elif level < 40:
            return "Commander"
        elif level < 50:
            return "Captain"
        elif level < 60:
            return "Admiral"
        else:
            return "Fleet Admiral"

    # ── Item Generation ───────────────────────────────────────────────

    def _find_item(self, nick: str, level: int) -> GameEvent | None:
        """Generate a random item find for a player."""
        slot = random.choice(EQUIPMENT_SLOTS)
        max_item_level = int(level * 1.5)

        # Roll for item level (higher levels are rarer)
        item_level = 1
        for i in range(1, max_item_level + 1):
            if random.random() < (1 / (1.4 ** i)):
                item_level = i

        current_equipment = self.db.get_equipment(nick)
        current_item = next(
            (e for e in current_equipment if e["slot"] == slot), None
        )

        if current_item and current_item["item_level"] >= item_level:
            return None  # Current item is better

        # Generate sci-fi item name
        prefix = random.choice(ITEM_PREFIXES.get(slot, ["Advanced"]))
        suffix = random.choice(ITEM_SUFFIXES)
        item_name = f"{prefix} {suffix}"

        self.db.upgrade_item(nick, slot, item_name, item_level)

        msg = (
            f"{nick} found: [{item_name}] (Lv.{item_level}) "
            f"in slot [{slot.replace('_', ' ').title()}]!"
        )
        self.db.log_event("item_find", msg, nick)
        return GameEvent("item_find", msg, [nick])

    # ── Combat ────────────────────────────────────────────────────────

    def _trigger_battle(self, nick: str, level: int) -> GameEvent | None:
        """Trigger a battle between the player and a random online player."""
        online = self.db.get_online_players()
        opponents = [p for p in online if p["nick"] != nick]
        if not opponents:
            return None

        opponent = random.choice(opponents)

        attacker_sum = self.db.get_item_sum(nick)
        defender_sum = self.db.get_item_sum(opponent["nick"])

        # Alignment modifiers
        player_data = self.db.get_player(nick)
        if player_data and player_data["alignment"] == "good":
            attacker_sum = int(attacker_sum * 1.10)
        elif player_data and player_data["alignment"] == "evil":
            attacker_sum = int(attacker_sum * 0.90)

        if opponent["alignment"] == "good":
            defender_sum = int(defender_sum * 1.10)
        elif opponent["alignment"] == "evil":
            defender_sum = int(defender_sum * 0.90)

        atk_roll = random.randint(0, max(1, attacker_sum))
        def_roll = random.randint(0, max(1, defender_sum))

        if atk_roll >= def_roll:
            winner, loser = nick, opponent["nick"]
            msg = random.choice(BATTLE_WIN_MESSAGES).format(winner=winner, loser=loser)
            # Winner gains: reduce TTL
            opp_level = opponent["level"]
            pct = max(opp_level / 4, 7) / 100
            p = self.db.get_player(winner)
            if p:
                reduction = p["ttl_seconds"] * pct
                self.db.update_ttl(winner, reduction)
            # Loser penalty
            p2 = self.db.get_player(loser)
            if p2:
                penalty_pct = max(opp_level / 7, 7) / 100
                penalty = p2["ttl_seconds"] * penalty_pct
                self.db.add_penalty(loser, penalty)
        else:
            winner, loser = opponent["nick"], nick
            msg = random.choice(BATTLE_LOSE_MESSAGES).format(winner=winner, loser=loser)
            # Reverse rewards
            p = self.db.get_player(winner)
            if p:
                pct = max(level / 4, 7) / 100
                reduction = p["ttl_seconds"] * pct
                self.db.update_ttl(winner, reduction)
            p2 = self.db.get_player(loser)
            if p2:
                penalty_pct = max(level / 7, 7) / 100
                penalty = p2["ttl_seconds"] * penalty_pct
                self.db.add_penalty(loser, penalty)

        self.db.log_event("battle", msg, f"{winner},{loser}")
        return GameEvent("battle", msg, [winner, loser])

    # ── Random Events ─────────────────────────────────────────────────

    def _check_random_events(
        self, player: dict, online_players: list[dict]
    ) -> list[GameEvent]:
        """Check for random events (calamities, blessings, encounters)."""
        events = []
        nick = player["nick"]

        # Calamity
        if random.random() < self.config.event_calamity_chance:
            pct = random.uniform(5, 12)
            penalty = player["ttl_seconds"] * (pct / 100)
            self.db.add_penalty(nick, penalty)
            msg = random.choice(CALAMITY_MESSAGES[:3]).format(
                nick=nick, pct=f"{pct:.1f}"
            )
            events.append(GameEvent("calamity", msg, [nick]))
            self.db.log_event("calamity", msg, nick)

        # Blessing
        if random.random() < self.config.event_blessing_chance:
            pct = random.uniform(5, 12)
            bonus = player["ttl_seconds"] * (pct / 100)
            self.db.update_ttl(nick, bonus)
            msg = random.choice(BLESSING_MESSAGES[:3]).format(
                nick=nick, pct=f"{pct:.1f}"
            )
            events.append(GameEvent("blessing", msg, [nick]))
            self.db.log_event("blessing", msg, nick)

        return events

    # ── Penalties ──────────────────────────────────────────────────────

    def apply_penalty(self, nick: str, penalty_type: str, msg_length: int = 0) -> str:
        """Apply a penalty to a player and return the message."""
        player = self.db.get_player(nick)
        if not player:
            return ""

        level = player["level"]
        base = 1.14 ** level

        penalties = {
            "nick": self.config.penalty_nick * base,
            "part": self.config.penalty_part * base,
            "quit": self.config.penalty_quit * base,
            "kick": self.config.penalty_kick * base,
            "msg": msg_length * self.config.penalty_msg_multiplier * base,
        }

        seconds = penalties.get(penalty_type, 0)
        if seconds <= 0:
            return ""

        self.db.add_penalty(nick, seconds)
        hours = seconds / 3600
        return (
            f"{nick} has been penalized {hours:.1f}h for "
            f"{penalty_type} (Lv.{level})."
        )

    # ── Player Info ───────────────────────────────────────────────────

    def get_status(self, nick: str) -> str:
        """Get player status string."""
        player = self.db.get_player(nick)
        if not player:
            return f"{nick} is not registered. Use: REGISTER <name> [role]"

        ttl_h = player["ttl_seconds"] / 3600
        item_sum = self.db.get_item_sum(nick)
        return (
            f"[{player['character_name']}] {player['crew_role']} | "
            f"Lv.{player['level']} | TTL: {ttl_h:.1f}h | "
            f"Gear: {item_sum} | W/L: {player['battles_won']}/{player['battles_lost']} | "
            f"Alignment: {player['alignment']}"
        )

    def get_top_list(self) -> str:
        """Get formatted top player list."""
        top = self.db.get_top_players(5)
        if not top:
            return "No crew members registered yet."
        lines = ["═══ Station Crew Rankings ═══"]
        for i, p in enumerate(top, 1):
            ttl_h = p["ttl_seconds"] / 3600
            lines.append(
                f"  {i}. {p['character_name']} [{p['crew_role']}] "
                f"Lv.{p['level']} (TTL: {ttl_h:.1f}h)"
            )
        return "\n".join(lines)
