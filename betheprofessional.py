import json
import os
import re
import string
import sys
import copy
from datetime import datetime
from sqlhelper import SQLHelper
from typing import Tuple, List, Union, Dict

import discord
from discord.ext import commands
from pytz import timezone

DEFAULT_MSG_LANG = "de"
PREFIX = "."

bot = commands.Bot(PREFIX, pm_help=True)
bot.remove_command("help")

with open("languages", mode="r", encoding="utf-8") as languages_file:
    default_languages = [line.strip() for line in languages_file.readlines()]
    sql = SQLHelper("servers.db", default_languages, DEFAULT_MSG_LANG)

translations = dict()
for lang_file in os.listdir("lang"):
    with open(f"lang/{lang_file}", mode="r", encoding="utf-8") as translation_file:
        translations[os.path.splitext(os.path.basename(lang_file))[0]] = json.load(translation_file)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")

    for guild in bot.guilds:
        if not sql.is_guild(guild.id):
            sql.add_guild(guild.id)

    print(f"I'm on {sql.get_guild_count()} servers.")


@bot.event
async def on_message(msg: discord.Message):
    if bot.user in msg.mentions:
        await send_translated(msg.channel, "type_help",
                              mention=msg.author.mention, command=bot.command_prefix + cmd_help.name)

    await bot.process_commands(msg)


def split_languages(args):
    args = rem_discord_markdown(args)
    return [arg.strip() for arg in args.strip(';').split(";")]


def get_translation(*keys: str, default=None, language=DEFAULT_MSG_LANG) -> Union[dict, str, float, bool]:
    if language.lower() not in translations:
        return default

    current = translations.get(language.lower())
    for key in keys:
        if type(current) is dict:
            current = current.get(key, None)
        elif current is None:
            current = translations.get(key, None)

    return copy.deepcopy(current) or default


@bot.command(name="+")
@commands.guild_only()
@commands.bot_has_permissions(manage_roles=True)
async def cmd_add_language(ctx: commands.Context, lang, *langs):
    args = split_languages(" ".join([lang, *langs]))
    if not args:
        await send_help(ctx.author)
        return

    prof = Professional(ctx.author)
    result, affected = await prof.add_languages(*args)

    await send_translated(ctx.channel, result, lang=", ".join(affected), mention=ctx.author.mention)


@bot.command(name="-")
@commands.guild_only()
@commands.bot_has_permissions(manage_roles=True)
async def cmd_remove_language(ctx: commands.Context, lang, *langs):
    args = split_languages(" ".join([lang, *langs]))
    if not args:
        await send_help(ctx.author)
        return

    prof = Professional(ctx.author)
    result, affected = await prof.remove_languages(*args)

    await send_translated(ctx.channel, result, lang=", ".join(affected), mention=ctx.author.mention)


@bot.command(name="*")
@commands.guild_only()
@commands.bot_has_permissions(manage_roles=True)
@commands.has_permissions(manage_roles=True)
async def cmd_register_language(ctx: commands.Context, lang, *langs):
    args = " ".join([lang, *langs])
    if args == "":
        await send_help(ctx.author)
        return

    if discord.utils.find(lambda role: role.name.lower() == args.lower(), ctx.guild.roles):
        await send_translated(ctx.channel, "create_lang_role_already_existing",
                              mention=ctx.author.mention, role=args)
        return

    success = sql.add_topic(ctx.guild.id, args)
    sql.commit()

    if not success:
        await send_translated(ctx.channel, "language_already_registered", mention=ctx.author.mention, lang=args)
        return

    await send_translated(ctx.channel, "language_registered",
                          mention=ctx.author.mention, lang=args)


@bot.command(name="/")
@commands.guild_only()
@commands.bot_has_permissions(manage_roles=True)
@commands.has_permissions(manage_roles=True)
async def cmd_unregister_language(ctx: commands.Context, lang, *langs):
    args = " ".join([lang, *langs])
    if args == "":
        await send_help(ctx.author)
        return

    success = sql.remove_topic(ctx.guild.id, args)
    sql.commit()

    if not success:
        await send_translated(ctx.channel, "language_not_found", mention=ctx.author.mention, lang=args)
        return

    await send_translated(ctx.channel, "language_unregistered", mention=ctx.author.mention, lang=args)


@bot.command(name="?")
async def cmd_help(ctx: commands.Context):
    await send_help(ctx.author)

    await ctx.message.add_reaction("✅")


@bot.command(name="°")
@commands.guild_only()
@commands.has_permissions(manage_roles=True)
async def cmd_set_translation(ctx: commands.Context, language):
    language = language.lower()
    if language not in translations:
        await ctx.message.add_reaction("❌")
        return

    sql.set_message_language(ctx.guild.id, language)
    sql.commit()
    await ctx.message.add_reaction("✅")


class Professional:
    def __init__(self, user: discord.Member):
        self.user = user
        self.guild: discord.Guild = user.guild

    def _update_topics(self):
        self.available_languages = {topic.lower(): topic for topic in sql.get_topics(self.guild.id)}
        return self.available_languages

    async def add_languages(self, *language: str) -> Tuple[str, List[str]]:
        self._update_topics()

        language = set(language)
        guild_missing_roles = []
        user_missing_roles = []
        for lang in language:
            if lang.lower() not in self.available_languages:
                return "language_not_found", [lang]
            if discord.utils.find(lambda r: r.name.lower() == lang.lower(), self.user.roles):
                return "user_has_language_already", [lang]
            add_role = discord.utils.find(lambda r: r.name.lower() == lang.lower(), self.user.guild.roles)
            if add_role:
                user_missing_roles.append(add_role)
            else:
                guild_missing_roles.append(lang.lower())

        for role in guild_missing_roles:
            role: discord.Role = await self.guild.create_role(name=self.available_languages[role], mentionable=True,
                                                              permissions=discord.Permissions.none())
            user_missing_roles.append(role)

        await self.user.add_roles(*user_missing_roles, reason="User added a language role")
        return "languages_added", [role.name for role in user_missing_roles]

    async def remove_languages(self, *language: str) -> Tuple[str, List[str]]:
        self._update_topics()

        language = set(language)
        if "*" in language:
            await self.user.remove_roles(*list(filter(lambda role: role.name.lower() in self.available_languages,
                                                      self.user.roles)))
            return "all_languages_removed", list()

        remove_roles = []
        for lang in language:
            if lang.lower() not in self.available_languages:
                return "language_not_existing", [lang]
            rem_role = discord.utils.find(lambda r: r.name.lower() == lang.lower(), self.user.roles)
            if not rem_role:
                return "language_not_yet_requested", [lang]
            remove_roles.append(rem_role)
        await self.user.remove_roles(*remove_roles, reason="User removed a language role")
        return "languages_removed", [role.name for role in remove_roles]


class PluralFormatter(string.Formatter):
    def get_value(self, key, args, kwargs):
        if isinstance(key, int):
            return args[key]
        if key in kwargs:
            return kwargs[key]
        if '(' in key and key.endswith(')'):
            key, rest = key.split('(', 1)
            plural = ", " in kwargs[key]
            suffix = rest.rstrip(')').split(',')
            if len(suffix) == 1:
                suffix.insert(0, '')
            return suffix[1] if plural else suffix[0]
        else:
            raise KeyError(key)


plural_formatter = PluralFormatter()


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.message.add_reaction("❓")
        await send_help(ctx.author)

    elif isinstance(error, commands.errors.CommandNotFound):
        pass

    elif isinstance(error, commands.errors.BotMissingPermissions):
        await send_translated(ctx.channel, "bot_no_permission", mention=ctx.author.mention)

    elif isinstance(error, commands.errors.MissingPermissions):
        await send_translated(ctx.channel, "no_permission", mention=ctx.author.mention)

    elif isinstance(error, commands.errors.NoPrivateMessage):
        await send_translated(ctx.channel, "private_channel")

    elif isinstance(error, commands.errors.DiscordException):
        print("Error ocurred:", error, file=sys.stderr)

    else:
        print(type(error), error, ctx.author, ctx.message, file=sys.stderr)


async def send_translated(channel: discord.abc.Messageable, key, **args):
    try:
        guild_origin = channel.guild if isinstance(channel, discord.TextChannel) else None
        language = sql.get_msg_language(guild_origin.id) if guild_origin else DEFAULT_MSG_LANG

        await channel.send(plural_formatter.format(get_translation(key, default="", language=language), **args))
    except discord.Forbidden:
        pass


async def send_help(user: discord.User):
    translation_lang = sql.get_msg_language(user.guild.id) if isinstance(user, discord.Member) else DEFAULT_MSG_LANG

    cmd_descriptions: Dict[str, Tuple[str, str]] = {cmd.name: (get_translation("commands", "syntax", cmd.name,
                                                                               language=translation_lang),
                                                               get_translation("commands", "description", cmd.name,
                                                                               language=translation_lang))
                                                    for cmd in bot.commands}

    cmd__help = [f"``{cmd}{(' ' + syntax) if syntax else ''}``"
                 f" {desc.format(translations=', '.join(translations.keys())) if desc else ''}"
                 for cmd, (syntax, desc) in cmd_descriptions.items()]

    cmd__help = "\n".join(cmd__help)

    embed_data: dict = get_translation("help_embed", language=translation_lang)

    if embed_data and isinstance(embed_data, dict):
        if "fields" in embed_data and isinstance(embed_data["fields"], list):
            languages = sql.get_topics(user.guild.id) if isinstance(user, discord.Member) else default_languages
            languages.sort()

            field_formatting = dict(mention=user.mention, prefix=PREFIX, language_amount=len(languages),
                                    commands=cmd__help, languages=", ".join(languages),
                                    guild_count=sql.get_guild_count(), translations=", ".join(translations.keys()))

            for f in embed_data["fields"]:
                if "name" in f and "value" in f:
                    f["name"] = f["name"].format(**field_formatting)
                    f["value"] = f["value"].format(**field_formatting)

            if "timestamp" in embed_data:
                embed_data["timestamp"] = embed_data["timestamp"].format(
                    timestamp=datetime.now(timezone("Europe/Berlin")).astimezone(timezone("UTC")).isoformat())

        help_embed = discord.Embed.from_dict(embed_data)

        if "footer" in embed_data and isinstance(embed_data["footer"], dict) and "text" in embed_data["footer"]:
            help_embed.set_footer(text=embed_data["footer"]["text"],
                                  icon_url=embed_data["footer"].get("icon_url", discord.Embed.Empty))

        await user.send(embed=help_embed)


def rem_discord_markdown(text: str) -> str:
    return re.sub(r"[`\n]+", "", text)


if __name__ == "__main__":
    sql.setup()
    try:
        bot.run(open("bot_token", mode="r").read())
    except KeyboardInterrupt:
        pass
    finally:
        sql.close()
