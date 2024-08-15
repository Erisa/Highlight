import datetime
import re

import dateutil
import humanize
import parsedatetime
from discord import app_commands
from discord.ext import commands

from . import formats

class ShortTime:
    """Attempts to parse a time using regex."""

    regex = re.compile(
        """(?:(?P<years>[0-9]+)(?:years?|year|y))?\s?
           (?:(?P<months>[0-9]+)(?:months?|month|mo))?\s?
           (?:(?P<weeks>[0-9]+)(?:weeks?|week|w))?\s?
           (?:(?P<days>[0-9]+)(?:days?|day|d))?\s?
           (?:(?P<hours>[0-9]+)(?:hours?|hour|h))?\s?
           (?:(?P<minutes>[0-9]+)(?:minutes?|minute|mins|min|m))?\s?
           (?:(?P<seconds>[0-9]+)(?:seconds?|second|secs|sec|s))?\s?""",
           re.VERBOSE)

    def __init__(self, argument, *, now=None):
        now = now or datetime.datetime.utcnow()
        match = self.regex.fullmatch(argument)
        if not match or not match.group(0):
            raise commands.BadArgument("You provided an invalid time")

        data = {key: int(value) for key, value in match.groupdict(default=0).items()}
        delta = dateutil.relativedelta.relativedelta(**data)

        self.delta = delta
        self.time = now+delta
        self.past = self.time < now

    @classmethod
    async def convert(cls, ctx, argument):
        return cls(argument, now=ctx.message.created_at.replace(tzinfo=None))

class HumanTime:
    """Attempts to parse a time using parsedatetime."""

    calendar = parsedatetime.Calendar(version=parsedatetime.VERSION_CONTEXT_STYLE)

    def __init__(self, argument, *, now=None):
        now = now or datetime.datetime.utcnow()
        time, context = self.calendar.parseDT(argument, sourceTime=now)
        if not context.hasDateOrTime:
            # No date or time data
            raise commands.BadArgument("I couldn't recognize your time. Try something like `tomorrow` or `3 days`.")
        if not context.hasTime:
            # We have the date, but not the time, so replace it with the time
            time = time.replace(hour=now.hour, minute=now.minute, second=now.second, microsecond=now.microsecond)

        self.time = time
        self.past = time < now

    @classmethod
    async def convert(cls, ctx, argument):
        return cls(argument, now=ctx.message.created_at.replace(tzinfo=None))

class Time:
    """Attempts to parse the time using HumanTime and then ShortTime."""

    def __init__(self, argument, *, now=None):
        now = now or datetime.datetime.utcnow()
        try:
            # Attempt to parse the time through ShortTime
            parsed = ShortTime(argument, now=now)
        except commands.BadArgument:
            # Otherwise use HumanTime
            parsed = HumanTime(argument, now=now)

        self.time = parsed.time
        self.past = parsed.past

    @classmethod
    async def convert(cls, ctx, argument):
        return cls(argument, now=ctx.message.created_at.replace(tzinfo=None))

class FutureTime(Time):
    """Attempts to parse a time using Time but then checks if it's in the future."""

    def __init__(self, argument, *, now=None):
        super().__init__(argument, now=now)
        if self.past:
            raise commands.BadArgument("That time is in the past")

class TimeWithContent(Time):
    """Attempts to parse a time by using ShortTime regex or parsedatetime.Calendar.nlp and then stripping the content from the time."""

    def __init__(self, argument, *, now=None):
        now = now or datetime.datetime.utcnow()

        # Attempt to parse the time using ShortTime regex
        match = ShortTime.regex.match(argument)
        if match and match.group(0):
            data = {key: int(value) for key, value in match.groupdict(default=0).items()}
            time = now+dateutil.relativedelta.relativedelta(**data)
            content = argument[match.end():].strip()
        else:
            # nlp doesn't work with 'from now' so handle that here
            if argument.endswith("from now"):
                argument = argument[:-8].strip()

            parsed = HumanTime.calendar.nlp(argument, sourceTime=now)
            if not parsed:
                raise commands.BadArgument("I couldn't recognize your time. Try something like `tomorrow` or `3 days`.")
            time, context, start, end, text = parsed[0]

            if not context.hasDateOrTime:
                raise commands.BadArgument("I couldn't recognize your time. Try something like `tomorrow` or `3 days`.")
            if not context.hasTime:
                # We have date date data, but not time, so replace it with time data
                time = time.replace(hour=now.hour, minute=now.minute, second=now.second, microsecond=now.microsecond)
            if context.accuracy == parsedatetime.pdtContext.ACU_HALFDAY:
                time = time.replace(day=now.day+1)

            if start != 0 and end != len(argument):
                # Time does not start at the start but it doesn't end at the end either
                raise commands.BadArgument("The time must be at the start or end of the argument not the middle, like `do homework in 3 hours` or `in 3 hours do homework`")
            if time < now:
                raise commands.BadArgument("That time is in the past")

            if start:
                content = argument[:start].strip()
            else:
                content = argument[end:].strip()

        if not content:
            content = "..."

        self.time = time
        self.past = time < now
        self.content = content

def timedelta(time, *, when=None, accuracy=3):
    now = when or datetime.datetime.utcnow()

    # Get rid of microseconds
    now = now.replace(microsecond=0)
    time = time.replace(microsecond=0)

    # Delta and suffix stuff
    if time > now:
        delta = dateutil.relativedelta.relativedelta(time, now)
        suffix = ""
    else:
        delta = dateutil.relativedelta.relativedelta(now, time)
        suffix = " ago"

    units = ["year", "month", "day", "hour", "minute", "second"]
    output = []

    for unit in units:
        item = getattr(delta, f"{unit}s")
        if item and unit == "day":
            weeks = delta.weeks
            if weeks:
                item -= weeks * 7
                output.append(format(formats.plural(weeks), "week"))

        if item:
            output.append(format(formats.plural(item), unit))

    if accuracy:
        output = output[:accuracy]

    if len(output) == 0:
        return "now"
    else:
        return formats.join(output, last="and") + suffix

class BadTimeTransform(app_commands.AppCommandError):
    pass

class TimeTransformer(app_commands.Transformer):
    async def transform(self, interaction, value):
        now = interaction.created_at.replace(tzinfo=None)
        try:
            short = ShortTime(value, now=now)
        except commands.BadArgument:
            try:
                human = FutureTime(value, now=now)
            except commands.BadArgument as exc:
                raise BadTimeTransform(str(exc)) from None
            else:
                return human.time
        else:
            return short.time

def format_time(time):
    return time.strftime("%b %d, %Y at %H:%M:%S")

def fulltime(time, use_humanize=True):
    if use_humanize:
        return f"{humanize.naturaldate(time)} ({humanize.naturaltime(time)})"
    else:
        return f"{format_time(time)} ({timedelta(time)})"
