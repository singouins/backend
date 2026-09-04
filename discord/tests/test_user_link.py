# -*- coding: utf8 -*-

from unittest.mock import MagicMock, patch

import discord
import pytest
from email_validator import validate_email as real_validate_email

from subcommands.user.link import link as link_command


def _validate_no_dns(email, **kwargs):
    # Same syntax validation as production, minus the MX/DNS lookup, so
    # these tests don't depend on outbound network access.
    return real_validate_email(email, check_deliverability=False)


@pytest.fixture(autouse=True)
def _no_dns_email_validation():
    with patch('subcommands.user.link.validate_email', side_effect=_validate_no_dns):
        yield


@pytest.fixture
def bot_stub():
    # link()'s closure only reads bot.user.mention (to tell the caller
    # where to DM). It's a real discord.Bot's read-only property normally,
    # so a stub is simpler than faking a logged-in connection - it's
    # deliberately a different object from the `bot` fixture used to
    # create the command group, since the two roles don't need to match.
    stub = MagicMock()
    stub.user.mention = '<@123456789>'
    return stub


async def test_link_outside_dm_prompts_for_dm_and_skips_db(bot, bot_stub, make_ctx, get_callback, make_user):  # noqa: E501
    user = make_user(name='someone@example.com', discord={'name': None, 'ack': False})

    group = bot.create_group(name='user', description='test')
    link_command(group, bot_stub)
    callback = get_callback(group, 'link')

    ctx = make_ctx(channel_type=discord.ChannelType.text)
    await callback(ctx, 'someone@example.com')

    assert ctx.respond.call_count == 1
    assert ctx.author.send.call_count == 1
    user.reload()
    assert user.discord.name is None


async def test_link_invalid_email_responds_once(bot, bot_stub, make_ctx, get_callback):
    group = bot.create_group(name='user', description='test')
    link_command(group, bot_stub)
    callback = get_callback(group, 'link')

    ctx = make_ctx(channel_type=discord.ChannelType.private)
    await callback(ctx, 'not-an-email')

    assert ctx.respond.call_count == 1
    embed = ctx.respond.call_args.kwargs['embed']
    assert 'NotValid' in embed.description


async def test_link_unknown_mail_leaves_db_untouched(bot, bot_stub, make_ctx, get_callback, make_user):  # noqa: E501
    make_user(name='registered@example.com')

    group = bot.create_group(name='user', description='test')
    link_command(group, bot_stub)
    callback = get_callback(group, 'link')

    ctx = make_ctx(channel_type=discord.ChannelType.private)
    await callback(ctx, 'unregistered@example.com')

    assert ctx.respond.call_count == 1
    embed = ctx.respond.call_args.kwargs['embed']
    assert 'NotFound' not in embed.description  # sanity: didn't hit the wrong branch
    assert 'No User with mail' in embed.description


async def test_link_already_linked_is_idempotent(bot, bot_stub, make_ctx, get_callback, make_user):  # noqa: E501
    user = make_user(name='linked@example.com', discord={'name': 'existing_discord_name', 'ack': True})  # noqa: E501

    group = bot.create_group(name='user', description='test')
    link_command(group, bot_stub)
    callback = get_callback(group, 'link')

    ctx = make_ctx(author_name='someone_else', channel_type=discord.ChannelType.private)
    await callback(ctx, 'linked@example.com')

    assert ctx.respond.call_count == 1
    user.reload()
    assert user.discord.name == 'existing_discord_name'


async def test_link_success_persists_discord_identity(bot, bot_stub, make_ctx, get_callback, make_user):  # noqa: E501
    user = make_user(name='fresh@example.com', discord={'name': None, 'ack': False})

    group = bot.create_group(name='user', description='test')
    link_command(group, bot_stub)
    callback = get_callback(group, 'link')

    ctx = make_ctx(author_name='new_discord_user', channel_type=discord.ChannelType.private)
    await callback(ctx, 'fresh@example.com')

    assert ctx.respond.call_count == 1
    user.reload()
    assert user.discord.name == 'new_discord_user'
    assert user.discord.ack is True
