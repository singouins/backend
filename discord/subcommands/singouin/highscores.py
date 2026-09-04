# -*- coding: utf8 -*-

import discord

from discord.commands import option
from discord.ext import commands
from loguru import logger
from mongoengine import EmbeddedDocument

from mongo.models.Creature import CreatureDocument
from mongo.models.Highscore import HighscoreDocument

from subcommands.singouin._autocomplete import get_mysingouins_list
from subcommands.singouin._tools import creature_sprite


def highscores(group_singouin, bot):
    @group_singouin.command(
        description='[@Singouins role] Display your Singouin(s) HighScores',
        default_permission=False,
        name='highscores',
        )
    @commands.has_any_role('Singouins', 'Team')
    @option(
        "singouinuuid",
        description="Singouin UUID",
        autocomplete=get_mysingouins_list
        )
    async def highscores(
        ctx,
        singouinuuid: str,
    ):
        h = f'[#{ctx.channel.name}][{ctx.author.name}]'
        logger.info(f'{h} /{group_singouin} highscores {singouinuuid}')

        file = None

        try:
            Creature = CreatureDocument.objects(_id=singouinuuid).get()
            Highscore = HighscoreDocument.objects(_id=singouinuuid).get()
        except (CreatureDocument.DoesNotExist, HighscoreDocument.DoesNotExist):
            msg = 'Singouin NotFound'
            await ctx.respond(
                embed=discord.Embed(
                    description=msg,
                    colour=discord.Colour.orange()
                    ),
                ephemeral=True,
                )
            logger.info(f'{h} └──> Singouin-HighScore Query KO ({msg})')
            return

        """
        # We try to fetch the TOP1 HighScores
        try:
            maxhs_score = {}
            HighScores = HighscoreDocument.objects()
            if HighScores and HighScores.count() > 0:
                for HighScore in HighScores:
                    for key, val in HighScore.items():
                        if key == 'payload':
                            pass
                        elif key == 'id':
                            creatureuuid = val
                        else:
                            if key not in maxhs_score:
                                maxhs_score[key] = {
                                    "value": 0,
                                    "creature": None,
                                    }

                            if val and val >= maxhs_score[key]['value']:
                                maxhs_score[key]['value'] = val
                                maxhs_score[key]['creature'] = creatureuuid

        except Exception as e:
            msg = f'Max HighScores Query KO [{e}]'
            logger.error(msg)

        # We check if the Creature is the TOP1 or not
        medal = {}
        for hs in maxhs_score.keys():
            if maxhs_score[hs]['creature'] == Creature.id:
                medal[hs] = ':first_place: '
            else:
                medal[hs] = ''
        """

        embed = discord.Embed(
            title=f"{Creature.name} HighScores :trophy:",
            colour=discord.Colour.blue()
        )

        # Iterate over HighscoreDocument fields
        for field_name, field in Highscore._fields.items():
            if field_name in ['_id', 'created', 'updated', 'internal']:
                continue

            embed_field_value = ""
            value = getattr(Highscore, field_name)
            if isinstance(value, EmbeddedDocument):
                for sub_field_name, sub_field in value._fields.items():
                    sub_field_value = getattr(value, sub_field_name)
                    embed_field_value += f"> {sub_field_name} : `{sub_field_value}`\n"

            embed.add_field(
                name=f'**{field_name.capitalize()}:**',
                value=embed_field_value,
                inline=True,
                )

            # We check if we have a sprite to add as thumbnail
            if creature_sprite(Creature):
                file = discord.File(f'/tmp/{Creature.id}.png', filename=f'{Creature.id}.png')
                embed.set_thumbnail(url=f'attachment://{Creature.id}.png')

        await ctx.respond(embed=embed, ephemeral=True, file=file)
        logger.info(f'{h} └──> Singouin-HighScore Query OK')
