"""Tests for the counting game's self-delete rule.

Deleting your own count is disruptive: the next counter reads the channel,
sees the wrong last number, and takes the penalty for somebody else's
deletion. The first deletion is a warning (posting twice and removing the
duplicate is innocent), the second costs a timed block.

The guards matter as much as the punishment — the bot's own housekeeping
deletions, moderator cleanup, exempt staff, and a missing View Audit Log
permission must all leave members alone.
"""

from __future__ import annotations

import datetime

import pytest
from unittest.mock import AsyncMock, MagicMock

import config
from cogs import counting


GUILD = 1
CHANNEL = 2
MEMBER = 111111111111111111
EXEMPT = 966507927756234823
MOD = 999

ACTIVE_GAME = {
    "guild_id": GUILD,
    "channel_id": CHANNEL,
    "mode": "hard",
    "current_count": 40,
    "active": True,
    "block_minutes": 120,
}


@pytest.fixture(autouse=True)
def exempt_list(monkeypatch):
    monkeypatch.setattr(config, "COUNTING_EXEMPT_IDS", {EXEMPT})


@pytest.fixture
def cog(monkeypatch) -> counting.Counting:
    instance = counting.Counting(MagicMock())
    instance.bot.db = MagicMock()
    instance.bot.db.fetchone = AsyncMock(return_value=ACTIVE_GAME)
    instance.bot.db.execute = AsyncMock(return_value=1)
    instance._counting_channels = {GUILD: CHANNEL}

    # By default: audit log readable, and nobody else deleted the message.
    monkeypatch.setattr(counting, "audit_log_readable", AsyncMock(return_value=True))
    monkeypatch.setattr(counting, "find_message_deleter", AsyncMock(return_value=None))
    return instance


def make_message(
    *, author_id: int = MEMBER, content: str = "41", channel_id: int = CHANNEL,
    is_bot: bool = False, message_id: int = 5000,
) -> MagicMock:
    msg = MagicMock()
    msg.id = message_id
    msg.guild.id = GUILD
    msg.guild.name = "Test"
    msg.author.id = author_id
    msg.author.bot = is_bot
    msg.author.mention = f"<@{author_id}>"
    msg.channel.id = channel_id
    msg.channel.send = AsyncMock()
    msg.content = content
    return msg


# --------------------------------------------------------------------------- #
# The strike ladder
# --------------------------------------------------------------------------- #
async def test_first_deletion_warns_without_blocking(cog):
    cog.bot.db.fetchone = AsyncMock(return_value=None)  # no strikes yet
    msg = make_message()

    await cog._register_deletion(msg)

    sent = msg.channel.send.await_args.args[0]
    assert "can't play fair" in sent
    # A warning row, never a blocked_until.
    written = cog.bot.db.execute.await_args.args[0]
    assert "blocked_until" not in written


async def test_second_deletion_blocks(cog):
    cog.bot.db.fetchone = AsyncMock(side_effect=[{"strikes": 1}, {"block_minutes": 120}])
    msg = make_message()

    await cog._register_deletion(msg)

    written = cog.bot.db.execute.await_args.args[0]
    assert "blocked_until" in written
    assert "out of the counting game" in msg.channel.send.await_args.args[0]


async def test_block_message_only_pings_the_offender(cog):
    cog.bot.db.fetchone = AsyncMock(side_effect=[{"strikes": 1}, {"block_minutes": 120}])
    msg = make_message()

    await cog._register_deletion(msg)

    allowed = msg.channel.send.await_args.kwargs["allowed_mentions"]
    assert allowed.everyone is False
    assert [o.id for o in allowed.users] == [MEMBER]


# --------------------------------------------------------------------------- #
# Guards: who must NOT be punished
# --------------------------------------------------------------------------- #
async def test_bot_own_housekeeping_deletion_is_ignored(cog):
    """The no-chat rule deletes messages itself; that isn't the member's doing."""
    msg = make_message(content="hello")
    cog._bot_deleted.add(msg.id)
    cog._register_deletion = AsyncMock()

    await cog.on_message_delete(msg)

    cog._register_deletion.assert_not_awaited()
    assert msg.id not in cog._bot_deleted  # consumed


async def test_moderator_deletion_is_ignored(cog, monkeypatch):
    monkeypatch.setattr(
        counting, "find_message_deleter", AsyncMock(return_value=MagicMock(id=MOD))
    )
    cog._register_deletion = AsyncMock()

    await cog.on_message_delete(make_message())

    cog._register_deletion.assert_not_awaited()


async def test_exempt_staff_are_ignored(cog):
    cog._register_deletion = AsyncMock()
    await cog.on_message_delete(make_message(author_id=EXEMPT))
    cog._register_deletion.assert_not_awaited()


async def test_missing_audit_permission_stays_quiet(cog, monkeypatch):
    """Without the permission every deletion looks like a self-delete, so the
    rule must not blame anyone at random."""
    monkeypatch.setattr(counting, "audit_log_readable", AsyncMock(return_value=False))
    cog._register_deletion = AsyncMock()

    await cog.on_message_delete(make_message())

    cog._register_deletion.assert_not_awaited()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"is_bot": True},                  # the bot's own messages
        {"channel_id": 8888},              # a different channel
        {"content": "just chatting"},      # never a count attempt
        {"content": "$startgame"},         # an admin command
    ],
)
async def test_irrelevant_deletions_are_ignored(cog, kwargs):
    cog._register_deletion = AsyncMock()
    await cog.on_message_delete(make_message(**kwargs))
    cog._register_deletion.assert_not_awaited()


async def test_a_real_self_delete_is_punished(cog):
    """The positive case, so the guards above aren't just blocking everything."""
    cog._register_deletion = AsyncMock()
    await cog.on_message_delete(make_message())
    cog._register_deletion.assert_awaited_once()


async def test_inactive_game_is_ignored(cog):
    cog.bot.db.fetchone = AsyncMock(return_value={**ACTIVE_GAME, "active": False})
    cog._register_deletion = AsyncMock()

    await cog.on_message_delete(make_message())

    cog._register_deletion.assert_not_awaited()


# --------------------------------------------------------------------------- #
# Serving a block
# --------------------------------------------------------------------------- #
async def test_blocked_lookup_returns_the_expiry(cog):
    later = datetime.datetime(2030, 1, 1)
    cog.bot.db.fetchone = AsyncMock(return_value={"blocked_until": later})
    assert await cog._blocked_until(GUILD, MEMBER) == later


async def test_not_blocked_returns_none(cog):
    cog.bot.db.fetchone = AsyncMock(return_value=None)
    assert await cog._blocked_until(GUILD, MEMBER) is None


async def test_block_minutes_falls_back_to_the_default(cog):
    cog.bot.db.fetchone = AsyncMock(return_value=None)
    assert await cog._block_minutes(GUILD) == counting.DEFAULT_BLOCK_MINUTES
