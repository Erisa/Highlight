import discord
from discord.ext import commands
from discord.ext import tasks

import datetime
import humanize
import asyncio
import dateparser

class Timers(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.loop.start()

    def cog_unload(self):
        self.loop.cancel()

    async def create_timer(self, userid, event, time, extra):
        query = """INSERT INTO timers (userid, event, time, extra)
                   VALUES ($1, $2, $3, $4);
                """
        await self.bot.db.execute(query, userid, event, time, extra)

    async def cancel_timer(self, userid, event):
        query = """DELETE FROM timers
                   WHERE timers.userid=$1 AND timers.event=$2;
                """
        await self.bot.db.execute(query, userid, event)
 
    @tasks.loop(seconds=30)
    async def loop(self):
        query = """SELECT * FROM timers;"""
        timers = await self.bot.db.fetch(query)
        for timer in timers:
            time = timer["time"]-datetime.datetime.utcnow()
            if (time.seconds < 30 and time.days == 0) or (time.days < 0):
                self.bot.dispatch(f"{timer['event']}_complete", timer)
                query = """DELETE FROM timers
                           WHERE timers.id=$1;
                        """
                await self.bot.db.execute(query, timer["id"])

    @loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()

def setup(bot):
    bot.add_cog(Timers(bot))
