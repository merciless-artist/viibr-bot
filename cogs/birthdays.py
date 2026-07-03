"""Birthday tracker.

Members register their own birthday with /addmybd. A daily task announces the
day's birthdays in the configured channel, sending the premade greeting card
image and one of the birthday songs from the assets folder (rotating by day),
plus a button members can press to send wishes.
"""

from __future__ import annotations

import datetime
import logging
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands, tasks
from pymysql.err import IntegrityError

from utils import embeds
from utils.permissions import admin_only

log = logging.getLogger("vibe.birthdays")

WISH_BUTTON_ID = "viibr_bday_wish"

# Announcement time: 14:00 UTC (9 AM Central / 10 AM Eastern).
ANNOUNCE_TIME = datetime.time(hour=14, minute=0, tzinfo=datetime.timezone.utc)

ASSETS_DIR = Path(__file__).resolve().parent.parent / "ASSETS" / "birthday tracker"
CARD_IMAGE = ASSETS_DIR / "birthday-message.png"
SONGS_DIR = ASSETS_DIR / "mp3s"


def todays_song(today: datetime.date) -> Path | None:
    """Pick the day's birthday song from the assets folder, rotating daily.

    The folder is scanned at send time, so new songs added to the repository
    join the rotation automatically.
    """
    songs = sorted(SONGS_DIR.glob("*.mp3"))
    if not songs:
        return None
    return songs[today.timetuple().tm_yday % len(songs)]


class BirthdayWishView(discord.ui.View):
    """Persistent view holding the 'Send birthday wishes' button."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Send birthday wishes",
        style=discord.ButtonStyle.primary,
        emoji="\N{BIRTHDAY CAKE}",
        custom_id=WISH_BUTTON_ID,
    )
    async def send_wishes(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ) -> None:
        cog = interaction.client.get_cog("Birthdays")
        if cog is None:
            await interaction.response.send_message(
                "Birthdays are unavailable right now.", ephemeral=True
            )
            return
        await cog.record_wish(interaction)


class Birthdays(commands.Cog):
    """Self-service birthday registration and daily announcements."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @property
    def db(self):
        return self.bot.db

    async def cog_load(self) -> None:
        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS vibe_birthdays (
                id INT AUTO_INCREMENT PRIMARY KEY,
                guild_id BIGINT NOT NULL,
                user_id BIGINT NULL,
                name VARCHAR(100) NULL,
                month INT NOT NULL,
                day INT NOT NULL,
                song_url VARCHAR(500) NULL,
                personal_message VARCHAR(500) NULL,
                added_by BIGINT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_member (guild_id, user_id),
                INDEX idx_date (guild_id, month, day)
            )
            """
        )
        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS vibe_bday_config (
                guild_id BIGINT PRIMARY KEY,
                channel_id BIGINT NULL,
                image_url VARCHAR(500) NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    ON UPDATE CURRENT_TIMESTAMP
            )
            """
        )
        await self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS vibe_bday_wishes (
                id INT AUTO_INCREMENT PRIMARY KEY,
                message_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE KEY unique_wish (message_id, user_id)
            )
            """
        )

        self.bot.add_view(BirthdayWishView())
        if not self.announce_birthdays.is_running():
            self.announce_birthdays.start()

    async def cog_unload(self) -> None:
        self.announce_birthdays.cancel()

    # -- Member slash commands -------------------------------------------------

    @app_commands.command(name="addmybd", description="Add your birthday to the server calendar")
    @app_commands.describe(month="Month (1-12)", day="Day (1-31)")
    async def add_my_birthday(
        self,
        interaction: discord.Interaction,
        month: app_commands.Range[int, 1, 12],
        day: app_commands.Range[int, 1, 31],
    ) -> None:
        await self.db.execute(
            "INSERT INTO vibe_birthdays (guild_id, user_id, month, day) "
            "VALUES (%s, %s, %s, %s) "
            "ON DUPLICATE KEY UPDATE month = VALUES(month), day = VALUES(day)",
            (interaction.guild_id, interaction.user.id, month, day),
        )
        await interaction.response.send_message(
            f"Your birthday is saved as **{month:02d}/{day:02d}**. "
            "Use /removemybd if you change your mind.",
            ephemeral=True,
        )

    @app_commands.command(name="removemybd", description="Remove your birthday from the calendar")
    async def remove_my_birthday(self, interaction: discord.Interaction) -> None:
        removed = await self.db.execute(
            "DELETE FROM vibe_birthdays WHERE guild_id = %s AND user_id = %s",
            (interaction.guild_id, interaction.user.id),
        )
        text = (
            "Your birthday has been removed from the calendar."
            if removed
            else "You don't have a birthday on the calendar."
        )
        await interaction.response.send_message(text, ephemeral=True)

    @app_commands.command(name="calendar", description="See upcoming birthdays")
    async def calendar(self, interaction: discord.Interaction) -> None:
        rows = await self.db.fetchall(
            "SELECT user_id, name, month, day FROM vibe_birthdays WHERE guild_id = %s",
            (interaction.guild_id,),
        )
        if not rows:
            await interaction.response.send_message(
                "No birthdays on the calendar yet. Add yours with /addmybd!",
                ephemeral=True,
            )
            return

        today = datetime.date.today()

        def days_until(row: dict) -> int:
            for year in (today.year, today.year + 1):
                try:
                    candidate = datetime.date(year, row["month"], row["day"])
                except ValueError:  # Feb 29 in a non-leap year
                    continue
                if candidate >= today:
                    return (candidate - today).days
            return 400

        upcoming = sorted(rows, key=days_until)[:10]
        lines = []
        for row in upcoming:
            who = f"<@{row['user_id']}>" if row["user_id"] else f"**{row['name']}**"
            when = f"{row['month']:02d}/{row['day']:02d}"
            days = days_until(row)
            note = "today!" if days == 0 else f"in {days} day(s)"
            lines.append(f"{when} — {who} ({note})")

        embed = embeds.info("Upcoming birthdays", "\n".join(lines))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # -- Admin command -----------------------------------------------------------

    @commands.command(name="bdaychannel")
    @admin_only()
    async def bday_channel(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        """Set the channel where birthday announcements are posted."""
        await self.db.execute(
            "INSERT INTO vibe_bday_config (guild_id, channel_id) VALUES (%s, %s) "
            "ON DUPLICATE KEY UPDATE channel_id = VALUES(channel_id)",
            (ctx.guild.id, channel.id),
        )
        await ctx.send(
            embed=embeds.success(f"Birthday announcements will post in {channel.mention}.")
        )

    # -- Wishes button -----------------------------------------------------------

    async def record_wish(self, interaction: discord.Interaction) -> None:
        """Record one wish per member per announcement and update the count."""
        try:
            await self.db.execute(
                "INSERT INTO vibe_bday_wishes (message_id, user_id) VALUES (%s, %s)",
                (interaction.message.id, interaction.user.id),
            )
        except IntegrityError:
            await interaction.response.send_message(
                "You've already sent your birthday wishes for this one!",
                ephemeral=True,
            )
            return

        row = await self.db.fetchone(
            "SELECT COUNT(*) AS c FROM vibe_bday_wishes WHERE message_id = %s",
            (interaction.message.id,),
        )
        count = row["c"] if row else 1

        try:
            await interaction.message.edit(
                content=f"{interaction.message.content.splitlines()[0]}\n"
                f"\N{PARTY POPPER} **{count}** birthday wish(es) from the community!"
            )
        except (discord.HTTPException, IndexError):
            pass

        await interaction.response.send_message(
            "Your birthday wishes have been added. \N{BIRTHDAY CAKE}", ephemeral=True
        )

    # -- Daily announcement task ---------------------------------------------------

    @tasks.loop(time=ANNOUNCE_TIME)
    async def announce_birthdays(self) -> None:
        today = datetime.date.today()
        configs = await self.db.fetchall(
            "SELECT guild_id, channel_id FROM vibe_bday_config "
            "WHERE channel_id IS NOT NULL"
        )
        for config_row in configs:
            guild = self.bot.get_guild(config_row["guild_id"])
            if guild is None:
                continue
            channel = guild.get_channel(config_row["channel_id"])
            if not isinstance(channel, discord.TextChannel):
                continue

            rows = await self.db.fetchall(
                "SELECT * FROM vibe_birthdays "
                "WHERE guild_id = %s AND month = %s AND day = %s",
                (guild.id, today.month, today.day),
            )
            for row in rows:
                await self._send_greeting(channel, row, today)

    async def _send_greeting(
        self, channel: discord.TextChannel, row: dict, today: datetime.date
    ) -> None:
        """Send the premade card and the day's song for one birthday."""
        who = f"<@{row['user_id']}>" if row["user_id"] else f"**{row['name']}**"

        files = []
        if CARD_IMAGE.is_file():
            files.append(discord.File(CARD_IMAGE))
        else:
            log.warning("Birthday card image not found at %s", CARD_IMAGE)

        song = todays_song(today)
        if song is not None:
            files.append(discord.File(song))

        try:
            await channel.send(
                content=f"\N{BIRTHDAY CAKE} Happy Birthday {who}!",
                files=files,
                view=BirthdayWishView(),
            )
        except discord.HTTPException:
            log.exception("Failed to send birthday greeting in %s", channel.id)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Birthdays(bot))
