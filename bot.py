import discord
from discord.ext import commands

import aiohttp
import datetime
import json
import logging

import asyncpg
import yaml

log = logging.getLogger("highlight")
logging.basicConfig(
    level=logging.INFO,
    format="(%(asctime)s) %(levelname)s %(message)s",
    datefmt="%m/%d/%y - %H:%M:%S %Z"
)

extensions = [
    "cogs.admin",
    "cogs.highlight",
    "cogs.meta",
    "cogs.timers"
]


class OptionMissing(Exception):
    pass


class InvalidOption(Exception):
    pass


class HighlightBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents(guilds=True, messages=True, reactions=True, guild_reactions=True, guild_typing=True)
        super().__init__(command_prefix=commands.when_mentioned, description="I DM you if I find one of your words in the chat", intents=intents)

        self.uptime = datetime.datetime.utcnow()
        self.support_server_link = "https://discord.gg/eHxvStNJb7"
        self.config = self.load_config()

        self.load_extension("jishaku")
        self.get_cog("Jishaku").hidden = True

        for extension in extensions:
            try:
                self.load_extension(extension)
            except Exception as exc:
                log.error("Couldn't load extension %s", extension, exc_info=exc)

    def load_config(self):
        with open("config.yml") as file:
            config = yaml.safe_load(file)

        if "token" not in config:
            raise OptionMissing("A Discord API token is required to run the bot, but was not found in config.yml")
        elif "database-uri" not in config:
            raise OptionMissing("A database URI is required for functionality, but was not found in config.yml")

        if "auto-update" not in config:
            config["auto-update"] = True
        if "console" not in config:
            config["console"] = None

        if not isinstance(config["token"], str):
            raise InvalidOption("The Discord API token must be a string")
        elif not isinstance(config["database-uri"], str):
            raise InvalidOption("The database URI must be a string")
        elif not isinstance(config["auto-update"], bool):
            raise InvalidOption("Auto-update must either be True or False")

        return config

    async def create_pool(self):
        async def init(connection): await connection.set_type_codec("jsonb", schema="pg_catalog", encoder=json.dumps, decoder=json.loads, format="text")
        self.db = await asyncpg.create_pool(self.config["database-uri"], init=init)

        with open("schema.sql") as file:
            schema = file.read()
            await self.db.execute(schema)

        query = """SELECT *
                   FROM words;
                """
        cached_words = await self.db.fetch(query)
        self.cached_words = [dict(cached_word) for cached_word in cached_words]

    async def on_connect(self):
        if not hasattr(self, "session"):
            self.session = aiohttp.ClientSession()

        if not hasattr(self, "db"):
            await self.create_pool()

    async def on_ready(self):
        log.info(f"Logged in as {self.user.name} - {self.user.id}")
        self.console = self.get_channel(self.config["console"])

    async def close(self):
        await super().close()
        await self.db.close()
        await self.session.close()

    def run(self):
        super().run(self.config["token"])


bot = HighlightBot()
bot.run()
