import datetime
import json
import logging

import aiohttp
import asyncpg
import discord
from discord.ext import commands

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

def userStrOverride(self):
    if self.discriminator == "0":
        return self.name
    return f"{self.name}#{self.discriminator}"

discord.User.__str__ = userStrOverride

class OptionMissing(Exception):
    pass


class InvalidOption(Exception):
    pass


class HighlightBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents(guilds=True, members=True, messages=True, reactions=True, guild_typing=True, message_content=True)
        allowed_mentions = discord.AllowedMentions(everyone=False, users=False, roles=False)
        super().__init__(command_prefix=commands.when_mentioned, description="I DM you if I find one of your words in the chat", intents=intents, allowed_mentions=allowed_mentions, case_insensitive=True)

        self.uptime = datetime.datetime.utcnow()
        self.support_server_invite = "https://discord.gg/XkWXRJ9fMv"

        self.status_webhook = None
        self.console = None

    async def setup_hook(self):
        log.info("Loading Jishaku")
        await self.load_extension("jishaku")

        log.info("Loading extensions")
        for extension in extensions:
            try:
                await self.load_extension(extension)
            except Exception as exc:
                log.error("Couldn't load extension %s", extension, exc_info=exc)

        log.info("Creating session")
        self.session = aiohttp.ClientSession()

        log.info("Getting webhooks")
        if getattr(self.config, "status_hook", None):
            self.status_webhook = discord.Webhook.from_url(self.config.status_hook, session=self.session)

        if getattr(self.config, "console_hook", None):
            self.console = discord.Webhook.from_url(self.config.console_hook, session=self.session)

        log.info("Connecting with database")
        async def init(connection): await connection.set_type_codec("jsonb", schema="pg_catalog", encoder=json.dumps, decoder=json.loads, format="text")
        self.db = await asyncpg.create_pool(self.config.database_uri, init=init)

        with open("schema.sql") as file:
            schema = file.read()
            await self.db.execute(schema)

        log.info("Preparing highlight word cache")
        query = """SELECT *
                   FROM words;
                """
        cached_words = await self.db.fetch(query)
        self.cached_words = [dict(cached_word) for cached_word in cached_words]

    async def on_ready(self):
        log.info(f"Logged in as {self.user.name} - {self.user.id}")

        if self.status_webhook:
            await self.status_webhook.send("Recevied READY event")

    async def on_connect(self):
        if self.status_webhook:
            await self.status_webhook.send("Connected to Discord")

    async def on_disconnect(self):
        if self.status_webhook and not self.session.closed:
            await self.status_webhook.send("Disconnected from Discord")

    async def on_resumed(self):
        if self.status_webhook:
            await self.status_webhook.send("Resumed connection with Discord")

    async def close(self):
        await super().close()
        await self.db.close()

    def run(self):
        super().run(self.config.token)

    @discord.utils.cached_property
    def config(self):
        return __import__("config")

bot = HighlightBot()
bot.run()
