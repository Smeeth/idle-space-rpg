"""IRC Bot – connects to IRC, handles messages, runs the game loop."""

import asyncio
import logging
import ssl

import irc.client_aio
import irc.strings
from jaraco.stream import buffer

from .config import Config
from .database import Database
from .game_engine import GameEngine, CREW_ROLES

logger = logging.getLogger("idle-space-rpg")

HELP_TEXT = (
    "═══ Idle Space RPG Commands ═══ | "
    "REGISTER <name> [role] – Join the crew | "
    "STATUS [nick] – View status | "
    "TOP – Leaderboard | "
    "EQUIPMENT [nick] – View gear | "
    "ALIGN <good|neutral|evil> – Set alignment | "
    "HELP – This message | "
    f"Roles: {', '.join(CREW_ROLES)}"
)


class IdleSpaceBot:
    """Main IRC bot that runs the Idle Space RPG."""

    def __init__(self, config: Config):
        self.config = config
        self.db = Database(
            host=config.database.host,
            port=config.database.port,
            user=config.database.user,
            password=config.database.password,
            database=config.database.database,
        )
        self.engine = GameEngine(self.db, config.game)
        self.reactor = irc.client_aio.AioReactor()
        self.connection = None
        self._game_loop_task = None

    async def start(self):
        """Connect to IRC and start the game loop."""
        try:
            factory = irc.connection.AioFactory()
            if self.config.irc.use_tls:
                ssl_ctx = ssl.create_default_context()
                factory = irc.connection.AioFactory(ssl=ssl_ctx)

            server = self.reactor.server()
            self.connection = await server.connect(
                self.config.irc.server,
                self.config.irc.port,
                self.config.irc.nickname,
                connect_factory=factory,
            )

            # Register event handlers
            self.connection.add_global_handler("welcome", self._on_connect)
            self.connection.add_global_handler("pubmsg", self._on_pubmsg)
            self.connection.add_global_handler("privmsg", self._on_privmsg)
            self.connection.add_global_handler("join", self._on_join)
            self.connection.add_global_handler("part", self._on_part)
            self.connection.add_global_handler("quit", self._on_quit)
            self.connection.add_global_handler("nick", self._on_nick)
            self.connection.add_global_handler("kick", self._on_kick)
            self.connection.add_global_handler("namreply", self._on_names)

            logger.info(
                "Connected to %s:%d", self.config.irc.server, self.config.irc.port
            )

            # Start game loop
            self._game_loop_task = asyncio.create_task(self._game_loop())

            # Run the IRC event loop
            await self.reactor.process_forever()

        except Exception as e:
            logger.error("Connection error: %s", e)
            raise

    def _on_connect(self, connection, event):
        """Handle successful connection."""
        logger.info("Connected! Joining %s", self.config.irc.channel)
        if self.config.irc.nickserv_pass:
            connection.privmsg(
                "NickServ", f"IDENTIFY {self.config.irc.nickserv_pass}"
            )
        connection.join(self.config.irc.channel)

    def _on_join(self, connection, event):
        """Handle user joining the channel."""
        nick = event.source.nick
        if nick == self.config.irc.nickname:
            logger.info("Joined %s", self.config.irc.channel)
            return
        player = self.db.get_player(nick)
        if player:
            self.db.set_online(nick, True)
            logger.info("Player %s is now online", nick)

    def _on_part(self, connection, event):
        """Handle user leaving the channel."""
        nick = event.source.nick
        player = self.db.get_player(nick)
        if player:
            self.db.set_online(nick, False)
            msg = self.engine.apply_penalty(nick, "part")
            if msg:
                connection.privmsg(self.config.irc.channel, msg)

    def _on_quit(self, connection, event):
        """Handle user quitting IRC."""
        nick = event.source.nick
        player = self.db.get_player(nick)
        if player:
            self.db.set_online(nick, False)
            msg = self.engine.apply_penalty(nick, "quit")
            if msg:
                connection.privmsg(self.config.irc.channel, msg)

    def _on_nick(self, connection, event):
        """Handle nickname changes (penalty!)."""
        old_nick = event.source.nick
        player = self.db.get_player(old_nick)
        if player:
            msg = self.engine.apply_penalty(old_nick, "nick")
            if msg:
                connection.privmsg(self.config.irc.channel, msg)

    def _on_kick(self, connection, event):
        """Handle user being kicked."""
        nick = event.arguments[0]
        player = self.db.get_player(nick)
        if player:
            self.db.set_online(nick, False)
            msg = self.engine.apply_penalty(nick, "kick")
            if msg:
                connection.privmsg(self.config.irc.channel, msg)

    def _on_names(self, connection, event):
        """Handle NAMES reply to detect who is already in the channel."""
        nicks = event.arguments[2].split()
        for raw_nick in nicks:
            nick = raw_nick.lstrip("@+%~&")
            if nick == self.config.irc.nickname:
                continue
            player = self.db.get_player(nick)
            if player:
                self.db.set_online(nick, True)

    def _on_pubmsg(self, connection, event):
        """Handle public channel messages."""
        nick = event.source.nick
        message = event.arguments[0].strip()

        # Apply message penalty for speaking
        player = self.db.get_player(nick)
        if player:
            penalty_msg = self.engine.apply_penalty(nick, "msg", len(message))
            # Only announce big penalties
            if penalty_msg and len(message) > 50:
                connection.privmsg(self.config.irc.channel, penalty_msg)

        # Parse commands (prefix: . or !)
        if message.startswith((".", "!")):
            self._handle_command(connection, nick, message[1:])

    def _on_privmsg(self, connection, event):
        """Handle private messages (same commands)."""
        nick = event.source.nick
        message = event.arguments[0].strip()
        if message.startswith((".", "!")):
            self._handle_command(connection, nick, message[1:], private=True)

    def _handle_command(
        self, connection, nick: str, command: str, private: bool = False
    ):
        """Route and execute bot commands."""
        target = nick if private else self.config.irc.channel
        parts = command.split(maxsplit=2)
        cmd = parts[0].lower() if parts else ""

        if cmd == "register":
            if len(parts) < 2:
                connection.privmsg(target, "Usage: REGISTER <character_name> [role]")
                return
            char_name = parts[1]
            role = parts[2] if len(parts) > 2 else ""
            result = self.engine.register(nick, char_name, role)
            if "Welcome" in result:
                self.db.set_online(nick, True)
            connection.privmsg(target, result)

        elif cmd == "status":
            query_nick = parts[1] if len(parts) > 1 else nick
            result = self.engine.get_status(query_nick)
            connection.privmsg(target, result)

        elif cmd == "top":
            result = self.engine.get_top_list()
            for line in result.split("\n"):
                connection.privmsg(target, line)

        elif cmd == "equipment" or cmd == "eq":
            query_nick = parts[1] if len(parts) > 1 else nick
            equipment = self.db.get_equipment(query_nick)
            if not equipment:
                connection.privmsg(target, f"{query_nick} has no equipment.")
                return
            connection.privmsg(target, f"═══ {query_nick}'s Loadout ═══")
            for item in equipment:
                slot = item["slot"].replace("_", " ").title()
                connection.privmsg(
                    target,
                    f"  [{slot}] {item['item_name']} (Lv.{item['item_level']})",
                )

        elif cmd == "align":
            if len(parts) < 2 or parts[1].lower() not in ("good", "neutral", "evil"):
                connection.privmsg(target, "Usage: ALIGN <good|neutral|evil>")
                return
            alignment = parts[1].lower()
            self.db.update_alignment(nick, alignment)
            connection.privmsg(
                target, f"{nick} has aligned with the {alignment} faction."
            )

        elif cmd == "help":
            connection.privmsg(target, HELP_TEXT)

        else:
            connection.privmsg(target, f"Unknown command: {cmd}. Try .help")

    async def _game_loop(self):
        """Main game tick loop."""
        logger.info(
            "Game loop started (tick every %ds)", self.config.game.tick_interval
        )
        while True:
            await asyncio.sleep(self.config.game.tick_interval)
            try:
                events = self.engine.process_tick(self.config.game.tick_interval)
                for event in events:
                    if self.connection and self.connection.is_connected():
                        self.connection.privmsg(
                            self.config.irc.channel, event.message
                        )
            except Exception as e:
                logger.error("Game loop error: %s", e)

    def shutdown(self):
        """Clean shutdown."""
        if self._game_loop_task:
            self._game_loop_task.cancel()
        # Set all players offline
        self.db.set_all_offline()
        self.db.close()
        logger.info("Bot shut down.")
