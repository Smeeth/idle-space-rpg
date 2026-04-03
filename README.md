# Idle Space RPG 🚀

An IRC idle game bot set on a space station. Inspired by [IdleRPG](http://idlerpg.net/), but in a sci-fi setting.

Players join the crew of a space station, level up by idling in the IRC channel, find equipment, engage in automated combat, and experience random events – all without lifting a finger.

## Game Mechanics

### Core Concept
- **Stay online, level up.** The longer you idle in the channel, the more experience you gain.
- **Don't talk!** Speaking in the channel adds penalty time to your next level.
- Quitting, parting, nick changes, and getting kicked all add penalties.

### Crew Roles & Ranks
As you level up, your rank increases:

| Level Range | Rank |
|------------|------|
| 1–4 | Recruit |
| 5–9 | Crewman |
| 10–19 | Ensign |
| 20–29 | Lieutenant |
| 30–39 | Commander |
| 40–49 | Captain |
| 50–59 | Admiral |
| 60+ | Fleet Admiral |

### Equipment
10 gear slots with sci-fi themed items:
- Neural Implant, Suit, Weapon, Shield, Boots, Gloves, Helm, Amulet, Charm, Ring

Items are found on level-up. Higher levels = chance for better gear.

### Events
- **Battles** – Automated PvP based on gear scores
- **Calamities** – Solar flares, meteorite hits, rogue AI attacks
- **Blessings** – Alien data caches, nanobot upgrades, wormhole echoes
- **Quests** – Group missions for high-level crew (planned)

### Alignment
Choose **good**, **neutral**, or **evil**:
- Good: +10% gear score in battles, chance for cooperative XP boosts
- Evil: -10% gear score, but chance to steal XP from others, higher crit chance
- Neutral: No modifiers

## Commands

| Command | Description |
|---------|-------------|
| `.register <name> [role]` | Join the crew |
| `.status [nick]` | View your or another player's status |
| `.top` | Show leaderboard |
| `.equipment [nick]` | View gear loadout |
| `.align <good\|neutral\|evil>` | Set alignment |
| `.help` | Show help |

## Quick Start

### Docker (recommended)

```bash
cp .env.example .env
# Edit .env with your IRC server and MariaDB credentials
docker compose up -d
```

### Local Development

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env (set DB_HOST to your MariaDB host)
python -m bot
```

## Docker Integration

This bot runs alongside your existing IRC infrastructure. The stack includes a MariaDB 11 container for game state persistence. To connect to your Ergo IRCd Docker network:

```yaml
# In docker-compose.yml, uncomment and adjust:
networks:
  irc-net:
    external: true
    name: your_ergo_network_name
```

## Project Structure

```
idle-space-rpg/
├── bot/
│   ├── __init__.py
│   ├── __main__.py       # Entry point
│   ├── config.py         # Configuration (env vars)
│   ├── database.py       # MariaDB persistence
│   ├── game_engine.py    # Core game logic
│   └── irc_bot.py        # IRC connection & commands
├── tests/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

## License

MIT

## Credits

Inspired by the original [IdleRPG](http://idlerpg.net/) by jotun.
