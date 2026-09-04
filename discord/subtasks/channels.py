# -*- coding: utf8 -*-

import asyncio
import discord
import re

from loguru import logger
from typing import Dict, Union

from mongo.models.Korp import KorpDocument
from mongo.models.Squad import SquadDocument


def get_all_from_mongo(channel_type: str):
    GroupDocument = {
        'Korp': KorpDocument,
        'Squad': SquadDocument
    }.get(channel_type)

    if not GroupDocument:
        logger.error(f"Invalid channel_type: {channel_type}")
        return None

    try:
        groups = GroupDocument.objects()
        logger.trace('GroupDocument Query OK')
        return groups
    except GroupDocument.DoesNotExist:
        logger.debug("GroupDocument Query KO (404)")
        return None


async def ensure_channel_exists(
    guild: discord.Guild,
    channel_name: str,
    category: discord.CategoryChannel,
    overwrites: Dict[Union[discord.Role, discord.Member], discord.PermissionOverwrite]
):
    """Ensure the role exists in the guild. If not, create it.

    Args:
        guild (discord.Guild): The guild where the role should be created.
        role_name (str): The name of the role to create.

    Returns:
        Optional[discord.Role]: The created or existing role, or None if creation failed.
    """
    channel = discord.utils.get(guild.channels, name=channel_name)
    if channel:
        logger.debug(f'Channel already exists: {channel_name}')
        return channel

    logger.info(f'Creating channel: {channel_name}')
    try:
        channel = await guild.create_text_channel(
            channel_name,
            category=category,
            overwrites=overwrites,
        )
        logger.info(f'Channel created successfully: {channel_name}')
        return channel
    except Exception as e:
        logger.error(f'Failed to create channel {channel_name}: {e}')
        return None


async def ensure_role_exists(guild: discord.Guild, role_name: str):
    """Ensure the role exists in the guild. If not, create it.

    Args:
        guild (discord.Guild): The guild where the role should be created.
        role_name (str): The name of the role to create.

    Returns:
        Optional[discord.Role]: The created or existing role, or None if creation failed.
    """
    role = discord.utils.get(guild.roles, name=role_name)
    if role:
        logger.debug(f'Role already exists: {role_name}')
        return role

    logger.info(f'Creating role: {role_name}')
    try:
        role = await guild.create_role(
            name=role_name,
            mentionable=True,
            permissions=discord.Permissions.none()
        )
        logger.info(f'Role created successfully: {role_name}')
        return role
    except Exception as e:
        logger.error(f'Failed to create role {role_name}: {e}')
        return None


async def ensure_channel_deletion(channel: discord.TextChannel) -> None:
    """Helper function to delete a channel."""
    try:
        logger.debug(f'Deleting channel: {channel.name}')
        await channel.delete()
        logger.info(f'Channel deleted: {channel.name}')
    except Exception as e:
        logger.error(f'Failed to delete channel {channel.name}: {e}')


async def ensure_role_deletion(guild: discord.Guild, role_name: str) -> None:
    """Helper function to delete a role."""
    group_role = discord.utils.get(guild.roles, name=role_name)
    if group_role:
        try:
            logger.debug(f'Deleting role: {role_name}')
            await group_role.delete()
            logger.info(f'Role deleted: {role_name}')
        except Exception as e:
            logger.error(f'Failed to delete role {role_name}: {e}')


async def create(bot: discord.Client, channel_type: str, timer: int):
    while bot.is_ready():
        for guild in bot.guilds:
            admin_role = discord.utils.get(guild.roles, name='Team')
            bot_role = discord.utils.get(guild.roles, name='BOTS')
            category = discord.utils.get(guild.categories, name=f'{channel_type}s')

            Groups = get_all_from_mongo(channel_type)
            if Groups is None:
                continue

            for Group in Groups.all():
                role_name = f"{channel_type}-{Group.id}"
                channel_name = role_name.lower()
                channel = discord.utils.get(bot.get_all_channels(), name=channel_name)
                if channel:
                    # Group channel already exists
                    logger.debug(f'Group channel exists (channel:{channel.name})')
                    continue

                # Ensure role exists
                group_role = await ensure_role_exists(guild, role_name)
                if not group_role:
                    continue  # Skip if role creation failed

                # Ensure channel exists
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(read_messages=False),
                    guild.me: discord.PermissionOverwrite(read_messages=True),
                    admin_role: discord.PermissionOverwrite(read_messages=True),
                    group_role: discord.PermissionOverwrite(read_messages=True),
                    bot_role: discord.PermissionOverwrite(read_messages=True),
                }
                await ensure_channel_exists(guild, channel_name, category, overwrites)

        await asyncio.sleep(timer)


async def cleanup(bot: discord.Client, channel_type: str, timer: int):
    while bot.is_ready():
        for guild in bot.guilds:
            for channel in guild.text_channels:
                m = re.search(rf"^{channel_type.lower()}-(?P<group_id>[\w\-]+)", channel.name)
                if not m:
                    continue

                # We are here if REGEX matched
                group_id = m.group('group_id')

                GroupDocument = {
                    'Korp': KorpDocument,
                    'Squad': SquadDocument
                }.get(channel_type)
                if not GroupDocument:
                    logger.error(f"Invalid channel_type: {channel_type}")
                    return None

                if GroupDocument.objects(_id=group_id).first():
                    continue

                # Delete the channel if the group doesn't exist
                await ensure_channel_deletion(channel)

                # Attempt to delete the associated role
                role_name = f'{channel_type}-{group_id}'
                await ensure_role_deletion(guild, role_name)

        await asyncio.sleep(timer)
