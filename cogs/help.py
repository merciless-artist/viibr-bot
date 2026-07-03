"""Help commands.

`$help` / `$viibr` sends the staff command menu image to admins/mods; members
who run it are pointed to the `/help` slash command. `/help` is the
member-facing overview and never lists admin commands.
"""

from __future__ import annotations

import logging
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from utils import embeds
from utils.permissions import is_mod

log = logging.getLogger("vibe.help")

# Bot developer, tagged in the member help menu for problem reports.
DEV_ID = 966507927756234823

STAFF_MENU_IMAGE = (
    Path(__file__).resolve().parent.parent / "ASSETS" / "StaffHelpMenu.png"
)

MEMBER_ABOUT = (
    "Customized Utility bot for this server. Members can use these slash commands:"
)

MEMBER_TICKET = (
    "**Head over to the tickets channel and hit the Open A Ticket button**, "
    "then look for the private channel that pops up in the tickets category "
    "with your username as the channel name. You can send your message to the "
    "staff there and someone will be there to help you as soon as possible."
)

MEMBER_COMMANDS = (
    "`/resources` — server links: website, Twitch, Reddit, YouTube\n"
    "`/addmybd` — add your birthday to the server calendar\n"
    "`/removemybd` — take your birthday off the calendar\n"
    "`/calendar` — see upcoming birthdays"
)

MEMBER_COUNTING = (
    "Join the counting game in the counting channel — post the next number, "
    "one per person. \N{HIGH VOLTAGE SIGN} means you got it, and big numbers "
    "get a celebration. No counting twice in a row — you get one warning, "
    "then the count resets to zero."
)

MEMBER_REPORT = (
    "**Notice any glitches or the commands not working for the bot?** "
    f"Tag <@{DEV_ID}> in the channel where your command failed with a note "
    "about what happened. Thank you!"
)

# Invisible field header (zero-width space) so the report note reads as its
# own paragraph without a visible title.
BLANK_FIELD_NAME = "​"


class Help(commands.Cog):
    """Help menus for staff and members."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(name="help", aliases=["viibr"])
    async def help_command(self, ctx: commands.Context) -> None:
        """Send the staff menu image. Members are pointed to /help."""
        if not (isinstance(ctx.author, discord.Member) and is_mod(ctx.author)):
            await ctx.send("That menu is for staff. Use `/help` to see your commands.")
            return

        if STAFF_MENU_IMAGE.is_file():
            await ctx.send(file=discord.File(STAFF_MENU_IMAGE))
        else:
            log.warning("Staff menu image missing at %s", STAFF_MENU_IMAGE)
            await ctx.send(
                "The staff menu image is missing from the deployment — "
                "check ASSETS/StaffHelpMenu.png."
            )

    @app_commands.command(
        name="help", description="What Viibr can do and how to use it"
    )
    async def slash_help(self, interaction: discord.Interaction) -> None:
        """Member-facing overview of the bot. Never lists admin commands."""
        embed = embeds.info("Viibr Bot Slash Commands", MEMBER_ABOUT)
        embed.add_field(name="/Ticket", value=MEMBER_TICKET, inline=False)
        embed.add_field(name="Slash commands", value=MEMBER_COMMANDS, inline=False)
        embed.add_field(name="Counting", value=MEMBER_COUNTING, inline=False)
        embed.add_field(name=BLANK_FIELD_NAME, value=MEMBER_REPORT, inline=False)
        embed.set_footer(text="More features are on the way!")
        await interaction.response.send_message(
            embed=embed,
            ephemeral=True,
            allowed_mentions=discord.AllowedMentions.none(),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Help(bot))
