import discord
from discord.ext import commands

import datetime
import humanize
import sys
import traceback

class HighlightHelpCommand(commands.HelpCommand):
    bottom_text = "\n\nKey: `<required> [optional]`. **Remove <> and [] when using the command**. \nFor more help join the [support server]({0})."

    async def send_bot_help(self, mapping):
        ctx = self.context
        bot = ctx.bot

        em = discord.Embed(title=f"{bot.user.name} Help", description=f"{bot.description}. If you need more help you can join the [support server]({bot.support_server_invite}).\n\n", color=discord.Color.blurple())
        em.set_thumbnail(url=bot.user.display_avatar.url)

        commands = await self.filter_commands(bot.commands)
        for command in commands:
            em.description += f"`{self.get_command_signature(command).strip()}` {f'- {command.description}' if command.description else ''}\n"

        em.description += "\n\nKey: `<required> [optional]`. **Remove <> and [] when using the command**."

        await ctx.send(embed=em)

    async def send_cog_help(self, cog):
        await self.context.send(f"No command called \"{cog}\" found.") # Fake, but I don't want the commands to be divided into categories

    async def send_command_help(self, command):
        ctx = self.context
        bot = ctx.bot

        em = discord.Embed(title=f"{command.name} {command.signature.strip()}", description=command.description or "", color=discord.Color.blurple())
        em.set_thumbnail(url=bot.user.display_avatar.url)

        if command.aliases:
            em.description += f"\nAliases: {', '.join(command.aliases)}"

        em.description += self.bottom_text.format(bot.support_server_invite)

        await ctx.send(embed=em)

    async def send_group_help(self, group):
        ctx = self.context
        bot = ctx.bot

        em = discord.Embed(title=group.name, description=group.description or "", color=discord.Color.blurple())
        em.set_thumbnail(url=bot.user.display_avatar.url)

        if group.aliases:
            em.description += f"\nAliases: {', '.join(group.aliases)}"

        commands = await self.filter_commands(group.commands)

        if commands:
            em.description += "\n"

        for command in commands:
            em.description += f"\n`{self.get_command_signature(command).strip()}` {f'- {command.description}' if command.description else ''}\n"

        em.description += self.bottom_text.format(bot.support_server_invite)

        await ctx.send(embed=em)

class Meta(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self._original_help_command = bot.help_command
        bot.help_command = HighlightHelpCommand()
        bot.help_command.cog = self

    def cog_unload(self):
        self.bot.help_command = self._original_help_command

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        print(f"Ignoring exception in command {ctx.command}:", file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

        if isinstance(error, commands.PrivateMessageOnly):
            await ctx.send("This command can only be used in DMs")
        elif isinstance(error, commands.NoPrivateMessage):
            await ctx.send("This command cannot be used in DMs")
        elif isinstance(error, commands.errors.BotMissingPermissions):
            perms_text = "\n".join([f"- {perm.replace('_', ' ').capitalize()}" for perm in error.missing_perms])
            await ctx.send(f":x: I am missing some permissions:\n {perms_text}") 
        elif isinstance(error, commands.errors.MissingRequiredArgument):
            await ctx.send(f":x: You are missing a argument: `{error.param.name}`")
        elif isinstance(error, commands.UserInputError):
            await ctx.send(f":x: {error}")
        elif isinstance(error, commands.errors.CommandOnCooldown):
            await ctx.send(f"You are on cooldown. Try again in {formats.plural(int(error.retry_after)):second}.")
        elif isinstance(error, commands.MaxConcurrencyReached):
            await ctx.send(f":x: {error}")

        if isinstance(error, commands.CommandInvokeError):
            em = discord.Embed(
                title=":warning: Error",
                description=f"An unexpected error has occured. If you're confused or think this is a bug you can join the [support server]({self.bot.support_server_invite}). \n```py\n{error}```",
                color=discord.Color.gold()
            )
            em.set_footer(text=self.bot.user.name, icon_url=self.bot.user.display_avatar.url)
            await ctx.send(embed=em)

            em = discord.Embed(title=":warning: Error", description="", color=discord.Color.gold())
            em.description += f"\nCommand: `{ctx.command}`"
            em.description += f"\nLink: [Jump]({ctx.message.jump_url})"
            em.description += f"\n\n```py\n{error}```\n"

            if self.bot.console:
                await self.bot.console.send(embed=em)

    @commands.hybrid_command(name="uptime", description="Check my uptime")
    async def uptime(self, ctx):
        delta = datetime.datetime.utcnow()-self.bot.uptime
        await ctx.send(f"I started up {humanize.naturaldelta(delta)} ago")

    @commands.hybrid_command(name="ping", description="Check my latency")
    async def ping(self, ctx):
        await ctx.send(f"My latency is {int(self.bot.latency*1000)}ms")

    @commands.hybrid_command(name="invite", description="Get a invite link to add me to your server")
    async def invite(self, ctx):
        perms = discord.Permissions.none()
        perms.read_messages = True
        perms.send_messages = True
        perms.send_messages_in_threads = True
        perms.manage_messages = True
        perms.embed_links = True
        perms.attach_files = True
        perms.read_message_history = True
        perms.add_reactions = True
        await ctx.send(f"<{discord.utils.oauth_url(self.bot.user.id, permissions=perms)}>")

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.content in (f"<@{self.bot.user.id}>", f"<@!{self.bot.user.id}>") and not message.author.bot:
            await message.reply(f":wave: Hello there!\n In order to get more info about me type: {self.bot.user.mention} help.")

async def setup(bot):
    await bot.add_cog(Meta(bot))
