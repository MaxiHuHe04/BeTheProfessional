import asyncio
import json
import re
import sys
import time
from datetime import datetime
from typing import Tuple, List, Union, Dict

import discord
from pytz import timezone
from discord.ext import commands

MSG_LANG = "de"
PREFIX = "."

bot = commands.Bot(PREFIX, pm_help=True)
bot.remove_command("help")


with open("languages", mode="r", encoding="utf-8") as languages_file:
    languages = {lang.strip().lower(): lang.strip() for lang in languages_file.readlines()}

with open(f"lang/{MSG_LANG}.json", mode="r", encoding="utf-8") as lang_file:
    msg_data: dict = json.load(lang_file)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")


def sort_file():
    global languages
    languages = sorted(languages)
    with open("languages", mode="w", encoding="utf-8") as f:
        for l in languages:
            f.write(l + "\n")


def split_languages(args):
    args = rem_discord_markdown(args)
    return [arg.strip() for arg in args.strip(';').split(";")]


def get_translation(*keys: str, default=None) -> Union[dict, str, float, bool]:
    current = None
    for key in keys:
        if type(current) is dict:
            current = current.get(key, None)
        elif current is None:
            current = msg_data.get(key, None)

    return current or default


@bot.command(name="+",
             description=get_translation("commands", "description", "+"),
             help=get_translation("commands", "syntax", "+"))
@commands.bot_has_permissions(manage_roles=True)
@commands.guild_only()
async def cmd_add_language(ctx: commands.Context, lang, *langs):
    args = split_languages(" ".join([lang, *langs]))
    if not args:
        await send_help(ctx.author)
        return

    prof = Professional(ctx.author)
    result, affected = await prof.add_languages(*args)

    await send_translated(ctx.channel, result, lang=", ".join(affected), mention=ctx.author.mention)


@bot.command(name="-",
             description=get_translation("commands", "description", "-"),
             help=get_translation("commands", "syntax", "-"))
@commands.bot_has_permissions(manage_roles=True)
@commands.guild_only()
async def cmd_remove_language(ctx: commands.Context, lang, *langs):
    args = split_languages(" ".join([lang, *langs]))
    if not args:
        await send_help(ctx.author)
        return

    prof = Professional(ctx.author)
    result, affected = await prof.remove_languages(*args)

    await send_translated(ctx.channel, result, lang=", ".join(affected), mention=ctx.author.mention)


@bot.command(name="*",
             description=get_translation("commands", "description", "*"),
             help=get_translation("commands", "syntax", "*"))
@commands.bot_has_permissions(manage_roles=True)
@commands.has_permissions(manage_roles=True)
@commands.guild_only()
async def cmd_register_language(ctx: commands.Context, lang, *langs):
    args = " ".join([lang, *langs])
    if args == "":
        await send_help(ctx.author)
        return

    if args.lower() in languages:
        await send_translated(ctx.channel, "language_already_registered", mention=ctx.author.mention, lang=args)
        return

    if discord.utils.find(lambda role: role.name.lower() == args.lower(), ctx.guild.roles):
        await send_translated(ctx.channel, "create_lang_role_already_existing",
                              mention=ctx.author.mention, role=args)
        return

    languages[args.lower()] = args
    await send_translated(ctx.channel, "language_registered",
                          mention=ctx.author.mention, lang=args)


@bot.command(name="/",
             description=get_translation("commands", "description", "/"),
             help=get_translation("commands", "syntax", "/"))
@commands.bot_has_permissions(manage_roles=True)
@commands.has_permissions(manage_roles=True)
@commands.guild_only()
async def cmd_unregister_language(ctx: commands.Context, lang, *langs):
    args = " ".join([lang, *langs])
    if args == "":
        await send_help(ctx.author)
        return

    if args.lower() not in languages:
        await send_translated(ctx.channel, "language_not_found", mention=ctx.author.mention, lang=args)
        return

    del languages[args.lower()]
    await send_translated(ctx.channel, "language_unregistered", mention=ctx.author.mention, lang=args)


@bot.command(name="?",
             description=get_translation("commands", "description", "?"))
async def cmd_help(ctx: commands.Context):
    await send_help(ctx.author)
    await send_translated(ctx.channel, "help_sent", mention=ctx.author.mention)


class Professional:
    def __init__(self, user: discord.Member):
        self.user = user
        self.guild: discord.Guild = user.guild
        self.available_languages = languages  # TODO: per-guild languages

    async def add_languages(self, *language: str) -> Tuple[str, List[str]]:
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
            role: discord.Role = await self.guild.create_role(name=languages[role], mentionable=True,
                                                              permissions=discord.Permissions.none())
            user_missing_roles.append(role)

        await self.user.add_roles(*user_missing_roles, reason="User added a language role")
        return "languages_added", [role.name for role in user_missing_roles]

    async def remove_languages(self, *language: str) -> Tuple[str, List[str]]:
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


@bot.event
async def on_command_error(ctx: commands.Context, error: commands.CommandError):
    if isinstance(error, commands.MissingRequiredArgument):
        await send_translated(ctx.channel, "help_sent", mention=ctx.author.mention)
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
        await channel.send(get_translation(key, default="").format(**args))
    except discord.Forbidden:
        pass


async def send_help(user: discord.User):
    cmd_descriptions: Dict[str, Tuple[str, str]] = {cmd.name: (cmd.help, cmd.description) for cmd in bot.commands}

    cmd__help = ["``{}{}``".format(cmd, (" " + syntax) if syntax else "") + (" {}".format(desc) if desc else "")
                 for cmd, (syntax, desc) in cmd_descriptions.items()]

    cmd__help = "\n".join(cmd__help)

    embed_data: dict = get_translation("help_embed")
    if embed_data and isinstance(embed_data, dict):
        if "fields" in embed_data and isinstance(embed_data["fields"], list):
            field_formatting = dict(mention=user.mention, prefix=PREFIX, language_amount=len(languages),
                                    commands=cmd__help, languages=", ".join(languages))

            for f in embed_data["fields"]:
                if "name" in f and "value" in f:
                    f["name"] = f["name"].format(**field_formatting)
                    f["value"] = f["value"].format(**field_formatting)

            if "timestamp" in embed_data:
                embed_data["timestamp"] = embed_data["timestamp"].format(
                    timestamp=datetime.now(timezone("Europe/Berlin")).astimezone(timezone("UTC")).isoformat())

        help_embed = discord.Embed.from_data(embed_data)

        if "footer" in embed_data and isinstance(embed_data["footer"], dict) and "text" in embed_data["footer"]:
            help_embed.set_footer(text=embed_data["footer"]["text"],
                                  icon_url=embed_data["footer"].get("icon_url", discord.Embed.Empty))

        await user.send(content=None, embed=help_embed)


def rem_discord_markdown(text: str) -> str:
    return re.sub(r"[`\n]+", "", text)


async def wait_until(predicate, timeout, period=0.25, *args, **kwargs):
    end = time.time() + timeout
    while time.time() < end:
        if predicate(*args, **kwargs):
            return True

        await asyncio.sleep(period)
    return False

if __name__ == "__main__":
    bot.run(open("bot_token", mode="r").read())
