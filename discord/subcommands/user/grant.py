# -*- coding: utf8 -*-

import discord

from loguru import logger
from discord.ext import commands

from mongo.models.Creature import CreatureDocument
from mongo.models.User import UserDocument


def grant(group_user, bot):
    @group_user.command(
        description='[@everyone] Update your Discord roles (Squad/Korp)',
        default_permission=False,
        name='grant',
        )
    @commands.guild_only()  # Hides the command from the menu in DMs
    async def grant(
        ctx,
    ):
        h = f'[#{ctx.channel.name}][{ctx.author.name}]'
        logger.info(f'{h} /{group_user} grant')

        # Get the User
        try:
            User = UserDocument.objects(discord__name=ctx.author.name).get()
        except UserDocument.DoesNotExist:
            logger.warning("UserDocument Query KO (404)")
            await ctx.respond(
                embed=discord.Embed(
                    description=f'Unknown Discord Name:`{ctx.author.name}` in DB',
                    colour=discord.Colour.orange(),
                    ),
                ephemeral=True,
                )
            return
        except Exception as e:
            logger.error(f'MongoDB Query KO [{e}]')

        # Get the Singouin role
        try:
            singouinrole = discord.utils.get(
                ctx.author.guild.roles,
                name='Singouins'
                )
        except Exception as e:
            await ctx.respond(
                embed=discord.Embed(
                    description=f'Discord get-role:Singouins KO\n[{e}]',
                    colour=discord.Colour.red(),
                    ),
                ephemeral=True,
                )
            return
        # Add the Singouin role to the user
        try:
            if singouinrole not in ctx.author.roles:
                await ctx.author.add_roles(singouinrole)
        except Exception as e:
            await ctx.respond(
                embed=discord.Embed(
                    description=f'Discord add-role:Singouins KO\n[{e}]',
                    colour=discord.Colour.red(),
                    ),
                ephemeral=True,
                )
            return

        # Apply Squad roles if needed
        guild = ctx.guild

        # Get the Singouin(s)
        try:
            Creatures = CreatureDocument.objects(account=User.id)
        except Exception as e:
            logger.error(f'MongoDB Query KO [{e}]')
        else:
            if Creatures.count() == 0:
                msg = f'No Singouins found in DB for `{ctx.author.name}`'
                logger.warning(msg)
                await ctx.respond(
                    embed=discord.Embed(
                        description=msg,
                        colour=discord.Colour.orange(),
                        ),
                    ephemeral=True,
                    )
                return

        for Creature in Creatures:
            # Korp management
            if Creature.korp.id:
                # Get the Korp role
                try:
                    korprole = discord.utils.get(
                        guild.roles,
                        name=f"Korp-{Creature.korp}"
                        )
                except Exception as e:
                    await ctx.respond(
                        embed=discord.Embed(
                            description=f"Discord get-role:Korp-{Creature.korp} KO\n[{e}]",
                            colour=discord.Colour.red(),
                            ),
                        ephemeral=True,
                        )
                    return
                # Add the Korp role to the user
                try:
                    if korprole not in ctx.author.roles:
                        await ctx.author.add_roles(korprole)
                except Exception as e:
                    await ctx.respond(
                        embed=discord.Embed(
                            description=f"Discord add-role:Korp-{Creature.korp} KO\n[{e}]",
                            colour=discord.Colour.red(),
                            ),
                        ephemeral=True,
                        )
                    return

            # Squad management
            if Creature.squad.id:
                # Get the Squad role to the user
                try:
                    squadrole = discord.utils.get(
                        guild.roles,
                        name=f"Squad-{Creature.squad.id}"
                        )
                except Exception as e:
                    await ctx.respond(
                        embed=discord.Embed(
                            description=f"Discord get-role:Squad-{Creature.squad.id} KO\n[{e}]",
                            colour=discord.Colour.red(),
                            ),
                        ephemeral=True,
                        )
                    return
                # Add the Squad role to the user
                try:
                    if squadrole not in ctx.author.roles:
                        await ctx.author.add_roles(squadrole)
                except Exception as e:
                    await ctx.respond(
                        embed=discord.Embed(
                            description=f"Discord add-role:Squad-{Creature.squad.id} KO\n[{e}]",
                            colour=discord.Colour.red(),
                            ),
                        ephemeral=True,
                        )
                    return

        logger.info(f'{h} ├──> Query OK')
        await ctx.respond(
            embed=discord.Embed(
                description="Discord & Squad/Korp grant :ok:",
                colour=discord.Colour.green()
                )
            )
        logger.info(f'{h} └──> Answer sent')
