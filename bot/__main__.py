"""Entry point for the Idle Space RPG Bot."""

import asyncio
import logging
import signal
import sys

from .config import Config
from .irc_bot import IdleSpaceBot


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logger = logging.getLogger("idle-space-rpg")

    config = Config()
    bot = IdleSpaceBot(config)

    def handle_shutdown(sig, frame):
        logger.info("Received signal %s, shutting down...", sig)
        bot.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    logger.info("Starting Idle Space RPG Bot...")
    logger.info("Server: %s:%d (TLS: %s)", config.irc.server, config.irc.port, config.irc.use_tls)
    logger.info("Channel: %s", config.irc.channel)

    asyncio.run(bot.start())


if __name__ == "__main__":
    main()
