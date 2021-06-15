import discord
from discord.ext import commands, menus, tasks

import asyncio
import asyncpg
import dateparser
import datetime
import humanize
import logging
import re
import typing

class DiscordConverter(commands.Converter):
    def mention_or_id(self, arg):
        match = re.match(r"([0-9]{15,21})$", arg) or re.match(r"<@!?([0-9]+)>$", arg)
        return match

    async def wait_for_ratelimit(self, ctx):
        async with ctx.typing():
            while ctx.bot.is_ws_ratelimited():
                await asyncio.sleep(5)

class Member(DiscordConverter):
    async def convert(self, ctx, arg):
        match = self.mention_or_id(arg)

        # ID or mention
        if match:
            int_arg = int(match.group(1))

            try:
                member = await ctx.guild.fetch_member(int_arg)
                return member
            except discord.HTTPException:
                pass

        # Split username and discriminator
        if len(arg) > 5 and arg[-5] == "#":
            discriminator = arg[-4:]
            username = arg[:-5]
        else:
            username = arg
            discriminator = None

        if ctx.bot.is_ws_ratelimited():
            await self.wait_for_ratelimit(ctx)

        # Query members by username
        members = await ctx.guild.query_members(query=username, limit=100, cache=False)
        for member in members:
            if member.name == username and (not discriminator or member.discriminator == discriminator):
                return member

        # Query members by nickname
        members = await ctx.guild.query_members(query=arg, limit=100, cache=False)
        for member in members:
            if member.nick == arg:
                return member

        raise commands.BadArgument(f"Member `{arg}` not found")

class User(DiscordConverter):
    async def convert(self, ctx, arg):
        match = self.mention_or_id(arg)

        # ID or mention
        if match:
            int_arg = int(match.group(1))

            try:
                member = await ctx.bot.fetch_user(int_arg)
                return member
            except discord.HTTPException:
                pass

        # Split username and discriminator
        if len(arg) > 5 and arg[-5] == "#":
            discriminator = arg[-4:]
            username = arg[:-5]
        else:
            username = arg
            discriminator = None

        if ctx.bot.is_ws_ratelimited():
            await self.wait_for_ratelimit(ctx)

        # Query members by username
        members = await ctx.guild.query_members(query=username, limit=100, cache=False)
        for member in members:
            if member.name == username and (not discriminator or member.discriminator == discriminator):
                return member

        raise commands.BadArgument(f"User `{arg}` not found")

class TimeConverter(commands.Converter):
    async def convert(self, ctx, arg):
        try:
            if not arg.startswith("in") and not arg.startswith("at"):
                arg = f"in {arg}"
            time = dateparser.parse(arg, settings={"TIMEZONE": "UTC"})
        except:
            raise commands.BadArgument("Failed to parse time")
        if not time:
            raise commands.BadArgument("Failed to parse time")
        return time

log = logging.getLogger("cogs.highlight")

class Highlight(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._highlight_batch = []
        self._batch_lock = asyncio.Lock(loop=bot.loop)

        self.bulk_insert_loop.add_exception_type(asyncpg.PostgresConnectionError)
        self.bulk_insert_loop.start()

    def cog_unload(self):
        self.bulk_insert_loop.stop()

    def cog_check(self, ctx):
        return ctx.guild

    @commands.Cog.listener("on_message")
    async def on_highlight(self, message):
        if not message.guild:
            return
        if message.author.bot:
            return

        # Search for any highlight words in the message

        notified_words = []
        possible_words = [word for word in self.bot.cached_words if word["guild_id"] == message.guild.id]

        for possible_word in possible_words:
            escaped = re.escape(possible_word["word"])
            match = re.match(r"^(?:.+ )?(?:\W*)({word})(?:[{word}]*)(?:\W+|[(?:'|\")s]*)(?: .+)?$".format(word=escaped), message.content, re.I)

            if match and possible_word["user_id"] not in [notified_word["user_id"] for notified_word in notified_words]:
                notified_words.append(possible_word)
                coroutine = self.send_highlight(message, possible_word, match.group(1))
                self.bot.loop.create_task(coroutine)

    @commands.Cog.listener()
    async def on_message(self, message):
        self.bot.dispatch("user_activity", message.channel, message.author)

    @commands.Cog.listener()
    async def on_typing(self, channel, user, when):
        self.bot.dispatch("user_activity", channel, user)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        self.bot.dispatch("user_activity", reaction.message.channel, user)

    async def send_highlight(self, message, word, text):
        try:
            member = await message.guild.fetch_member(word["user_id"])
        except discord.NotFound:
            log.info("Unknown user ID %s (guild ID %s)", word["user_id"], word["guild_id"])
            return

        query = """SELECT *
                   FROM settings
                   WHERE settings.user_id=$1;
                """
        settings = await self.bot.db.fetchrow(query, member.id)
        if not settings:
            settings = {"user_id": member.id, "disabled": False, "timezone": 0, "blocked_users": [], "blocked_channels": []}
        timezone = settings["timezone"]

        if member.id == message.author.id or settings["disabled"]:
            return
        if not message.channel.permissions_for(member).read_messages:
            return
        if message.channel.id in settings["blocked_channels"] or message.author.id in settings["blocked_users"]:
            return

        utc = ""
        if timezone == 0:
            utc = " UTC"

        description = f"In {message.channel.mention} for `{discord.utils.escape_markdown(message.guild.name)}` you were highlighted with the word **{discord.utils.escape_markdown(word['word'])}**\n\n"
        em = discord.Embed(description=description, timestamp=message.created_at, color=discord.Color.blurple())
        em.set_author(name=message.author.display_name, icon_url=message.author.avatar_url)
        em.add_field(name="Jump", value=f"[Jump!]({message.jump_url})")
        em.set_footer(text="Triggered")

        try:
            history = await message.channel.history(limit=3, before=message).flatten()
            messages = []
            for ms in reversed(history):
                content = f"{ms.content[:50]}{'...' if len(ms.content) > 50 else ''}"
                time = (ms.created_at+datetime.timedelta(hours=timezone)).strftime("%H:%M:%S")
                messages.append(f"`{time}{utc}` {discord.utils.escape_markdown(str(ms.author))}: {discord.utils.escape_markdown(content)}")
            em.description += "\n".join(messages)
        except discord.HTTPException:
            pass

        span = re.search(word["word"], message.content.lower()).span()
        content = discord.utils.escape_markdown(message.content[:span[0]])
        content += f"**{discord.utils.escape_markdown(text)}**"
        content += discord.utils.escape_markdown(message.content[span[1]:])

        content = f"{content[:50]}{'...' if len(content) > 50 else ''}"
        time = (message.created_at+datetime.timedelta(hours=timezone)).strftime("%H:%M:%S")
        em.description += f"\n> `{time}{utc}` {discord.utils.escape_markdown(str(message.author))}: {content}"

        def check(channel, user):
            return message.channel == channel and user == member

        # Wait 10 seconds to see if the user is active in the channel
        try:
            await self.bot.wait_for("user_activity", check=check, timeout=10)
            return
        except asyncio.TimeoutError:
            pass

        self._highlight_batch.append(
            {
                "guild_id": message.guild.id,
                "channel_id": message.channel.id,
                "message_id": message.id,
                "author_id": message.author.id,
                "user_id": word["user_id"],
                "word": word["word"],
                "invoked_at": message.created_at.isoformat()
            }
        )

        try:
            await member.send(embed=em)
        except discord.Forbidden:
            log.warning("Forbidden to DM user ID %s (guild ID %s)", member.id, message.guild.id)

    async def can_dm(self, user):
        try:
            await user.send()
        except discord.HTTPException as exc:
            if exc.code == 50006:
                return True
            elif exc.code == 50007:
                return False
            else:
                raise

    @commands.command(name="add", description="Add a word to your highlight list")
    async def add(self, ctx, *, word):
        word = word.lower()
        can_dm = await self.can_dm(ctx.author)

        if not can_dm:
            await ctx.send(":x: You need to enable DMs", delete_after=5)
        elif f"<@!{self.bot.user.id}>" in word:
            await ctx.send(":x: Your highlight word can't mention me", delete_after=5)
        elif len(word) < 2:
            await ctx.send(":x: Your word must be at least 2 characters", delete_after=5)
        elif len(word) > 20:
            await ctx.send(":x: Your word cannot be bigger than 20 characters", delete_after=5)
        else:
            try:
                query = """INSERT INTO words (user_id, guild_id, word)
                           VALUES ($1, $2, $3);
                        """
                await self.bot.db.execute(query, ctx.author.id, ctx.guild.id, word)

                self.bot.cached_words.append({"user_id": ctx.author.id, "guild_id": ctx.guild.id, "word": word})
                await ctx.send(f":white_check_mark: Added `{word}` to your highlight list", delete_after=5)
            except asyncpg.UniqueViolationError:
                await ctx.send(":x: You already have this word", delete_after=5)

        try:
           await ctx.message.delete()
        except discord.HTTPException:
            pass

    @commands.command(name="remove", description="Remove a word from your highlight list")
    async def remove(self, ctx, *, word):
        query = """DELETE FROM words
                   WHERE words.user_id=$1 AND words.guild_id=$2 AND words.word=$3;
                """
        result = await self.bot.db.execute(query, ctx.author.id, ctx.guild.id, word)

        if result == "DELETE 0":
            await ctx.send(":x: This word is not registered", delete_after=5)
        else:
            await ctx.send(f":white_check_mark: Removed `{word}` from your highlight list", delete_after=5)

        # Remove from cached words to avoid removed words triggering highlights
        for cached_word in self.bot.cached_words:
            if cached_word["user_id"] == ctx.author.id and cached_word["guild_id"] == ctx.guild.id and cached_word["word"] == word:
                self.bot.cached_words.remove(cached_word)

        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

    @commands.command(name="clear", description="Clear your highlight list")
    async def clear(self, ctx):
        query = """DELETE FROM words
                    WHERE words.user_id=$1 AND words.guild_id=$2;
                """
        result = await self.bot.db.execute(query, ctx.author.id, ctx.guild.id)

        await ctx.send(f":white_check_mark: Your highlight list has been cleared", delete_after=5)

        for cached_word in self.bot.cached_words:
            if cached_word["user_id"] == ctx.author.id and cached_word["guild_id"] == ctx.guild.id:
                self.bot.cached_words.remove(cached_word)

        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

    @commands.command(name="import", description="Import words from another server", usage="<server id>", aliases=["transfer"])
    async def transfer(self, ctx, guild_id: int):
        query = """SELECT *
                   FROM words
                   WHERE words.user_id=$1 AND (words.guild_id=$2 OR words.guild_id=$3);
                """
        words = await self.bot.db.fetch(query, ctx.author.id, guild_id, ctx.guild.id)
        words = [dict(word) for word in words]

        to_transfer = []
        for word in words:
            if word["guild_id"] == guild_id and word["word"] not in [word["word"] for word in words if word["guild_id"] == ctx.guild.id]:
                word["guild_id"] = ctx.guild.id
                to_transfer.append(word)

        if to_transfer:
            query = """INSERT INTO words (user_id, guild_id, word)
                       SELECT x.user_id, x.guild_id, x.word
                       FROM jsonb_to_recordset($1::jsonb) AS
                       x(user_id BIGINT, guild_id BIGINT, word TEXT);
                    """

            await self.bot.db.execute(query, to_transfer)
            await ctx.send(":white_check_mark: Your highlight list has been imported", delete_after=5)
        else:
            await ctx.send(":x: You have no words to transfer from this server", delete_after=5)

        for transfered in to_transfer:
            self.bot.cached_words.append(transfered)

        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

    @commands.command(name="show", description="View your highlight list", aliases=["words", "list"])
    async def show(self, ctx):
        words = [cached_word for cached_word in self.bot.cached_words if cached_word["user_id"] == ctx.author.id and cached_word["guild_id"] == ctx.guild.id]

        if not words:
            await ctx.send("You have no words for this server", delete_after=10)
        else:
            em = discord.Embed(title="Highlight Words", color=discord.Color.blurple())
            em.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url)

            em.description = ""
            for word in words:
                em.description += f"\n{word['word']}"

            await ctx.send(embed=em, delete_after=10)

        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

    @commands.command(name="block", description="Block a user or channel", usage="<user or channel>", aliases=["ignore", "mute"])
    async def block(self, ctx, *, user: typing.Union[User, discord.TextChannel]):
        query = """SELECT *
                   FROM settings
                   WHERE settings.user_id=$1;
                """
        settings = await self.bot.db.fetchrow(query, ctx.author.id)

        if isinstance(user, discord.User) or isinstance(user, discord.Member):
            if settings:
                if user.id in settings["blocked_users"]:
                    await ctx.send(":x: This user is already blocked", delete_after=5)
                else:
                    settings["blocked_users"].append(user.id)
                    query = """UPDATE settings
                               SET blocked_users=$1
                               WHERE settings.user_id=$2;
                            """
                    await self.bot.db.execute(query, settings["blocked_users"], ctx.author.id)
                    await ctx.send(f":no_entry_sign: Blocked `{user.display_name}`", delete_after=5)
            else:
                query = """INSERT INTO settings (user_id, disabled, timezone, blocked_users, blocked_channels)
                           VALUES ($1, $2, $3, $4, $5);
                        """
                await self.bot.db.execute(query, ctx.author.id, False, 0, [user.id], [])
        else:
            if settings:
                if user.id in settings["blocked_channels"]:
                    await ctx.send(":x: This channel is already blocked", delete_after=5)
                else:
                    settings["blocked_channels"].append(user.id)
                    query = """UPDATE settings
                               SET blocked_channels=$1
                               WHERE settings.user_id=$2;
                            """
                    await self.bot.db.execute(query, settings["blocked_channels"], ctx.author.id)
                    await ctx.send(f":no_entry_sign: Blocked {user.mention}", delete_after=5)
            else:
                query = """INSERT INTO settings (user_id, disabled, timezone, blocked_users, blocked_channels)
                           VALUES ($1, $2, $3, $4, $5);
                        """
                await self.bot.db.execute(query, ctx.author.id, False, 0, [], [user.id])

        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

    @commands.command(name="unblock", description="Unblock a user or channel", usage="<user or channel>", aliases=["unmute"])
    async def unblock(self, ctx, *, user: typing.Union[User, discord.TextChannel]):
        query = """SELECT *
                   FROM settings
                   WHERE settings.user_id=$1;
                """
        settings = await self.bot.db.fetchrow(query, ctx.author.id)

        if isinstance(user, discord.User) or isinstance(user, discord.Member):

            if settings:
                if user.id not in settings["blocked_users"]:
                    await ctx.send(":x: This user is not blocked", delete_after=5)
                else:
                    settings["blocked_users"].remove(user.id)
                    query = """UPDATE settings
                               SET blocked_users=$1
                               WHERE settings.user_id=$2;
                            """
                    await self.bot.db.execute(query, settings["blocked_users"], ctx.author.id)
                    await ctx.send(f":white_check_mark: Unblocked `{user.display_name}`", delete_after=5)
            else:
                await ctx.send(":x: This user is not blocked", delete_after=5)

        else:

            if settings:
                if user.id not in settings["blocked_channels"]:
                    await ctx.send(":x: This channel is not blocked", delete_after=5)
                else:
                    settings["blocked_channels"].remove(user.id)
                    query = """UPDATE settings
                               SET blocked_channels=$1
                               WHERE settings.user_id=$2;
                            """
                    await self.bot.db.execute(query, settings["blocked_channels"], ctx.author.id)
                    await ctx.send(f":white_check_mark: Unblocked {user.mention}", delete_after=5)
            else:
                await ctx.send(":x: This channel is not blocked")

        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

    @commands.group(name="blocked", description="View your blocked list", invoke_without_command=True)
    async def blocked(self, ctx):
        query = """SELECT *
                   FROM settings
                   WHERE settings.user_id=$1;
                """
        settings = await self.bot.db.fetchrow(query, ctx.author.id)

        if not settings or (not settings["blocked_channels"] and not settings["blocked_users"]):
            await ctx.send(":x: You have no channnels or users blocked", delete_after=5)
        else:
            em = discord.Embed(color=discord.Color.blurple())
            em.set_author(name=ctx.author.display_name, icon_url=ctx.author.avatar_url)

            users = []
            for user_id in settings["blocked_users"]:
                user = await self.bot.fetch_user(user_id)
                if user:
                    users.append(user.mention)

            if users:
                em.add_field(name="Blocked Users", value="\n".join(users))

            channels = []
            for channel_id in settings["blocked_channels"]:
                channel = self.bot.get_channel(channel_id)
                if channel:
                    channels.append(channel.mention)

            if channels:
                em.add_field(name="Blocked Channels", value="\n".join(channels))

            await ctx.send(embed=em, delete_after=10)
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

    @blocked.command(name="clear", description="Clear your blocked list")
    async def blocked_clear(self, ctx):
        query = """UPDATE settings
                   SET blocked_users=$1, blocked_channels=$2
                   WHERE settings.user_id=$3;
                """
        await self.bot.db.execute(query, [], [], ctx.author.id)

        await ctx.send(f":white_check_mark: Your blocked list has been cleared")

        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

    @commands.command(name="enable", description="Enable highlight")
    async def enable(self, ctx):
        await self.bot.get_cog("Timers").cancel_timer(ctx.author.id, "disable")

        query = """INSERT INTO settings (user_id, disabled, timezone, blocked_users, blocked_channels)
                   VALUES ($1, $2, $3, $4, $5)
                   ON CONFLICT (user_id)
                   DO UPDATE SET disabled=$2;
                """
        await self.bot.db.execute(query, ctx.author.id, False, 0, [], [])

        await ctx.send(":white_check_mark: Highlight has been enabled", delete_after=5)

        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

    @commands.command(name="disable", description="Disable highlight", aliases=["dnd"])
    async def disable(self, ctx, *, time: TimeConverter = None):
        await self.bot.get_cog("Timers").cancel_timer(ctx.author.id, "disable")

        query = """INSERT INTO settings (user_id, disabled, timezone, blocked_users, blocked_channels)
                   VALUES ($1, $2, $3, $4, $5)
                   ON CONFLICT (user_id)
                   DO UPDATE SET disabled=$2;
                """
        await self.bot.db.execute(query, ctx.author.id, True, 0, [], [])

        if time:
            await self.bot.get_cog("Timers").create_timer(ctx.author.id, "disabled", time, {})

        await ctx.send(f":white_check_mark: Highlight has been disabled {f'`for {humanize.naturaldelta(time-datetime.datetime.utcnow())}`' if time else ''}", delete_after=5)

        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

    @commands.command(name="timezone", description="Set your timezone")
    async def timezone(self, ctx, timezone: int = None):
        if timezone:
            query = """INSERT INTO settings (user_id, disabled, timezone, blocked_users, blocked_channels)
                       VALUES ($1, $2, $3, $4, $5)
                       ON CONFLICT (user_id)
                       DO UPDATE SET timezone=$3;
                    """

            await self.bot.db.execute(query, ctx.author.id, False, timezone, [], [])
            await ctx.send(f":white_check_mark: Timezone set to `{timezone}`", delete_after=5)

        else:
            query = """SELECT *
                       FROM settings
                       WHERE settings.user_id=$1;
                    """
            settings = await self.bot.db.fetchrow(query, ctx.author.id)
            if settings:
                await ctx.send(f"Your current timezone is `{settings['timezone']}`", delete_after=10)
            else:
                await ctx.send(f"Your current timezone is `{0}`", delete_after=10)

        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

    @commands.command(name="stats", description="View stats about the bot")
    async def stats(self, ctx):
        highlights = await self.bot.db.fetch("SELECT * FROM highlights;")

        em = discord.Embed(title="Highlight Stats", color=discord.Color.blurple())
        em.add_field(name="Total Highlights", value=len(highlights))
        em.add_field(name="Total Highlights Here", value=len([highlight for highlight in highlights if highlight["guild_id"] == ctx.guild.id]))
        await ctx.send(embed=em)

    @commands.Cog.listener()
    async def on_disabled_complete(self, timer):
        query = """INSERT INTO settings (user_id, disabled, timezone)
                   VALUES ($1, $2, $3)
                   ON CONFLICT (user_id)
                   DO UPDATE SET disabled=$2;
                """
        await self.bot.db.execute(query, timer["user_id"], False, 0)

    async def bulk_insert(self):
        query = """INSERT INTO highlights (guild_id, channel_id, message_id, author_id, user_id, word, invoked_at)
                   SELECT x.guild_id, x.channel_id, x.message_id, x.author_id, x.user_id, x.word, x.invoked_at
                   FROM jsonb_to_recordset($1::jsonb) AS
                   x(guild_id BIGINT, channel_id BIGINT, message_id BIGINT, author_id BIGINT, user_id BIGINT, word TEXT, invoked_at TEXT)
                """
        if self._highlight_batch:
            await self.bot.db.execute(query, self._highlight_batch)
            total = len(self._highlight_batch)
            self._highlight_batch.clear()

    @tasks.loop(seconds=20)
    async def bulk_insert_loop(self):
        async with self._batch_lock:
            await self.bulk_insert()

    @bulk_insert_loop.before_loop
    async def before_bulk_insert_loop(self):
        log.info("Waiting to start bulk insert loop")
        await self.bot.wait_until_ready()
        log.info("Starting bulk insert loop")

def setup(bot):
    bot.add_cog(Highlight(bot))
