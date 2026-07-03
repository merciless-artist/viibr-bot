"""General-purpose and health-check commands."""

from __future__ import annotations

from discord.ext import commands


class General(commands.Cog):
    """Basic commands used to confirm the bot is online."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="ping")
    async def ping(self, ctx: commands.Context) -> None:
        """Report the bot's current gateway latency."""
        latency_ms = round(self.bot.latency * 1000)
        await ctx.send(f"Pong! {latency_ms}ms")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(General(bot))
