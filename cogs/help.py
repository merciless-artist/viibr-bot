"""Help commands.

`$help` / `$amp` is the staff (admin/mod) menu; members who run it are pointed
to the `/help` slash command. `/help` is the member-facing overview and never
lists admin commands.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from utils import embeds
from utils.permissions import is_mod

# Bot developer, tagged in the member help menu for problem reports.
DEV_ID = 966507927756234823

ADMIN_ABOUT = "Customized Utility bot for this server. Responds only to the listed commands."

ADMIN_GENERAL = (
    "`$help` / `$viibr` — this menu\n"
    "`$ping` — check that the bot is online and responding"
)

ADMIN_TICKETS = (
    "*(admin & bot manager)*\n"
    "`$ticketstaff @role` — set the staff role pinged in new tickets\n"
    "`$ticketcategory <name>` — set the category tickets are created under\n"
    "`$ticketlog #channel` — set where closed-ticket transcripts are posted\n"
    "`$ticketconfig` — show the current ticket setup\n"
    "`$ticketpanel` — post the Open Ticket button in the current channel\n\n"
    "*(admin, bot manager and mods)*\n"
    "`$close` — close the ticket in the current channel"
)

ADMIN_MODERATION = (
    "*(admin, bot manager and mods)*\n"
    "`$delete <n>` — bulk delete the last n messages in this channel (max 100)\n\n"
    "*(admin & bot manager)*\n"
    "`$setlog #channel` — set the deletion log channel"
)

ADMIN_COUNTING = (
    "`$countinghard` — make this channel the counting channel (miscount resets)\n"
    "`$countingeasy` — counting channel, relaxed (miscounts don't reset)\n"
    "`$startgame` — start or restart the count\n"
    "`$milestone <number> <url>` — custom image/gif for a milestone number"
)

ADMIN_BIRTHDAYS = (
    "`$bdaychannel #channel` — where birthday announcements post\n"
    "Members add themselves with /addmybd; the card image and songs come "
    "from the repository's assets folder."
)

ADMIN_RESOURCES = (
    "`$addresource [Name](url)` — add a link to /resources\n"
    "`$deleteresource Name` — remove a link\n"
    "`$replaceresource [Name](new-url)` — update a link"
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
    "get a celebration."
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
        """Staff command menu. Members are pointed to /help."""
        if not (isinstance(ctx.author, discord.Member) and is_mod(ctx.author)):
            await ctx.send("That menu is for staff. Use `/help` to see your commands.")
            return

        embed = embeds.info("Admin/Mod Commands Menu", ADMIN_ABOUT)
        embed.add_field(name="General", value=ADMIN_GENERAL, inline=False)
        embed.add_field(name="Tickets", value=ADMIN_TICKETS, inline=False)
        embed.add_field(name="Moderation", value=ADMIN_MODERATION, inline=False)
        embed.add_field(name="Counting", value=ADMIN_COUNTING, inline=False)
        embed.add_field(name="Birthdays", value=ADMIN_BIRTHDAYS, inline=False)
        embed.add_field(name="Resources", value=ADMIN_RESOURCES, inline=False)
        embed.set_footer(text="Members: use /help for your version of this menu.")
        await ctx.send(embed=embed)

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
