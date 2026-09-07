# -*- coding: utf8 -*-

import asyncio
import discord

from kubernetes import client
from loguru import logger
from discord.commands import option
from discord.ext import commands
from kubernetes import config

from subcommands.infra._tools import log_pretty

#
# Globals used to build the ENV VAR for the batch
#
CUST_OUTPUT_PATH = '/var/www/websites'
CUST_DOMAIN = 'singouins.com'
CUST_SUBDOMAIN = 'games'


def deploy(group_admin):
    @group_admin.command(
        description='[@Team role] Deploy latest Front build',
        default_permission=False,
        name='deploy',
        )
    @commands.guild_only()  # Hides the command from the menu in DMs
    @commands.has_any_role('Team')
    @option(
        "env",
        description="Target environment",
        choices=['DEV', 'PROD'],
        )
    async def deploy(
        ctx,
        env: str,
    ):
        h = f'[#{ctx.channel.name}][{ctx.author.name}]'
        logger.info(f'{h} /{group_admin} deploy {env}')

        await ctx.defer()  # To defer answer (default: 15min)

        env = env.lower()
        namespace = 'singouins-networking'

        if env == 'dev':
            output_folder = f'{CUST_SUBDOMAIN}.dev.{CUST_DOMAIN}'
        else:
            output_folder = f'{CUST_SUBDOMAIN}.{CUST_DOMAIN}'

        try:
            config.load_kube_config("/etc/k8s/kubeconfig.yaml")
        except Exception as e:
            msg = f'K8s conf load KO [{e}]'
            logger.error(msg)
            embed = discord.Embed(
                description=msg,
                colour=discord.Colour.red()
                )
            await ctx.respond(embed=embed)
            return

        try:
            logger.info(f'{h} ├──> K8s Query Starting')

            app_name = 'front-deployer'
            pod_name = app_name
            pod_template = client.V1PodTemplateSpec(
                spec=client.V1PodSpec(
                    restart_policy="Never",
                    containers=[
                        client.V1Container(
                            image="alpine/git:2.36.2",
                            name=pod_name,
                            image_pull_policy="IfNotPresent",
                            volume_mounts=[
                                client.V1VolumeMount(name="websites", mount_path=CUST_OUTPUT_PATH),
                                client.V1VolumeMount(name="deployer-sh", mount_path='/code'),
                                ],
                            command=["/code/job-front-deployer.sh"],
                            env=[
                                client.V1EnvVar(name='CUST_GIT_BRANCH', value=f'build-{env}'),
                                client.V1EnvVar(name='CUST_OUTPUT_PATH', value=CUST_OUTPUT_PATH),
                                client.V1EnvVar(name='CUST_OUTPUT_FOLDER', value=output_folder),
                                client.V1EnvVar(
                                    name='CUST_GIT_QUIET',
                                    value_from=client.V1EnvVarSource(
                                        secret_key_ref=client.V1SecretKeySelector(  # noqa: E501
                                            name='git-secret',
                                            key='git-angular-quiet',
                                            )
                                        )
                                    ),
                                client.V1EnvVar(
                                    name='CUST_GIT_REPO',
                                    value_from=client.V1EnvVarSource(
                                        secret_key_ref=client.V1SecretKeySelector(  # noqa: E501
                                            name='git-secret',
                                            key='git-angular-repo',
                                            )
                                        )
                                    ),
                                client.V1EnvVar(
                                    name='CUST_GIT_USER',
                                    value_from=client.V1EnvVarSource(
                                        secret_key_ref=client.V1SecretKeySelector(  # noqa: E501
                                            name='git-secret',
                                            key='git-angular-user',
                                            )
                                        )
                                    ),
                                client.V1EnvVar(
                                    name='CUST_GIT_TOKEN',
                                    value_from=client.V1EnvVarSource(
                                        secret_key_ref=client.V1SecretKeySelector(  # noqa: E501
                                            name='git-secret',
                                            key='git-angular-token',
                                            )
                                        )
                                    ),
                                ],
                            )
                        ],
                    volumes=[
                        client.V1Volume(
                            name='websites',
                            persistent_volume_claim=client.V1PersistentVolumeClaimVolumeSource(  # noqa: E501
                                claim_name='nginx-www-pvc',
                                ),
                            ),
                        client.V1Volume(
                            name='deployer-sh',
                            config_map=client.V1ConfigMapVolumeSource(
                                items=[
                                    client.V1KeyToPath(
                                        key='deployer-sh',
                                        path='job-front-deployer.sh',
                                        mode=493,  # == 0755 permission
                                        )
                                    ],
                                name='deployer-configmap',
                                ),
                            ),
                        ],
                    ),
                metadata=client.V1ObjectMeta(
                    namespace=namespace,
                    name=pod_name,
                    labels={
                        "name": app_name,
                        },
                    ),
                )

            job = client.V1Job(
                api_version="batch/v1",
                kind="Job",
                metadata=client.V1ObjectMeta(
                    namespace=namespace,
                    name=f"{pod_name}-job",
                    ),
                spec=client.V1JobSpec(
                    backoff_limit=4,
                    parallelism=1,
                    completions=1,
                    template=pod_template,
                    ),
                )

            api_response = client.BatchV1Api().create_namespaced_job(
                body=job,
                namespace=namespace,
                )
            logger.debug(f'{h} ├──> K8s Query Ended')
        except Exception as e:
            logger.error(f'{h} └──> K8s Query KO [{e}]')
            embed = discord.Embed(
                description='Command aborted: K8s Query KO',
                colour=discord.Colour.red()
            )
            await ctx.respond(embed=embed)
            return
        else:
            # Job started
            description = '>> Job starting'
            await ctx.interaction.edit_original_response(
                embed=discord.Embed(
                    title=f'K8s deploy [{env}]',
                    description=description,
                    colour=discord.Colour.blue()
                    )
                )
            logger.info(f'{h} └──> K8s Query OK - Job created')

            job_completed = False
            while not job_completed:
                description = description + '.'
                await ctx.interaction.edit_original_response(
                    embed=discord.Embed(
                        title=f'K8s deploy [{env}]',
                        description=description,
                        colour=discord.Colour.blue()
                        )
                    )

                api_response = client.BatchV1Api().read_namespaced_job_status(
                    name=f"{pod_name}-job",
                    namespace=namespace,
                    )

                if api_response.status.succeeded is not None or \
                        api_response.status.failed is not None:
                    job_completed = True
                    logger.trace('K8s Query OK - Job completed')

                    description = description + '\n>> Job completed'
                    await ctx.interaction.edit_original_response(
                        embed=discord.Embed(
                            title=f'K8s deploy [{env}]',
                            description=description,
                            colour=discord.Colour.green()
                            )
                        )

                    try:
                        pod = client.CoreV1Api().list_namespaced_pod(
                            namespace,
                            label_selector=f"name={app_name}",
                            )
                        if len(pod.items) == 1:
                            log = client.CoreV1Api().read_namespaced_pod_log(
                                name=pod.items[0].metadata.name,
                                since_seconds=1728000,
                                namespace=namespace,
                                )
                            logger.trace(log)
                        else:
                            logger.warning('K8s Query OK - Logs NotFound')
                    except Exception as e:
                        logger.error(f'K8s Query KO [{e}]')
                    else:
                        logger.trace('K8s Query OK - Logs fetched')
                        description += '\n>> Job logs:\n```'

                        for line in log_pretty(log):
                            description += line
                            await ctx.interaction.edit_original_response(
                                embed=discord.Embed(
                                    title=f'K8s deploy [{env}]',
                                    description=f'{description}```',
                                    colour=discord.Colour.green()
                                    )
                                )

                    # Now we delete the Job
                    api_response = client.BatchV1Api().delete_namespaced_job(
                        name=f"{pod_name}-job",
                        namespace=namespace,
                        body=client.V1DeleteOptions(
                            propagation_policy='Foreground',
                            grace_period_seconds=0,
                            ),
                        )
                    description += '```>> Job deleting'
                    await ctx.interaction.edit_original_response(
                        embed=discord.Embed(
                            title=f'K8s deploy [{env}]',
                            description=description,
                            colour=discord.Colour.green()
                            )
                        )
                await asyncio.sleep(1)
            logger.trace('K8s Pods Query OK')

        logger.info(f'{h} └──> K8s Query OK')
        return
