import asyncio
import json
import re
from datetime import datetime
from typing import Tuple, Union, Set

import discord
from pytz import timezone

client = discord.Client()

MSG_LANG = "de"
PREFIX = "."

with open("languages", mode='r') as langFile:
    languages = langFile.readlines()

with open("lang/%s.json" % MSG_LANG, mode='r', encoding="utf-8") as msgLangFile:
    msg_data: dict = json.load(msgLangFile)

languages = [x.strip() for x in languages]
lowerLanguages = [lang.lower() for lang in languages]

commands = dict()
commandDescriptions = dict()


def sort_file():
    global languages, lowerLanguages
    languages = sorted(languages)
    lowerLanguages = [lang.lower() for lang in languages]
    with open("languages", mode="w", encoding="utf-8") as lang_file:
        for l in languages:
            lang_file.write(l + "\n")


def add_command(cmd: str, func, *, allow_private=False, permissions=0, user_permissions=0):
    commands[cmd.lower()] = (func, allow_private, permissions, user_permissions)
    commandDescriptions[cmd.lower()] = (get_msg_data("commands", "syntax", cmd, default=""),
                                        get_msg_data("commands", "description", cmd, default=""))


def init_commands():
    async def cmd_add_lang(args: str, msg: discord.Message):
        if args == "":
            await send_help(msg.author)
            return

        if ";" in args:
            result, affected = await add_languages(set(args.split(";")), msg.author)
        else:
            result = await add_language(args, msg.author)
            affected = args

        await send_translated_msg(msg.channel, "language_not_found" if result == 1 else
                                               "user_has_language_already" if result == 2 else
                                               "language_added",
                                  dict(lang=affected, mention=msg.author.mention))

    async def cmd_rem_lang(args: str, msg: discord.Message):
        if args == "":
            await send_help(msg.author)
            return

        result = await rem_language(args, msg.author)
        await send_translated_msg(msg.channel, "language_not_existing" if result == 1 else
                                               "language_not_yet_requested" if result == 2 else
                                               "all_languages_removed" if result == 3 else
                                               "language_removed", dict(lang=args, mention=msg.author.mention))

    async def cmd_create_lang(args: str, msg: discord.Message):
        if args == "":
            await send_help(msg.author)
            return

        if args.lower() in lowerLanguages:
            await send_translated_msg(msg.channel, "language_already_registered",
                                      dict(mention=msg.author.mention, lang=args))
            return

        if discord.utils.find(lambda role: role.name.lower() == args.lower(),  msg.server.roles):
            await send_translated_msg(msg.channel, "create_lang_role_already_existing",
                                      dict(mention=msg.author.mention,  role=args))
            return

        languages.append(args)
        sort_file()
        await send_translated_msg(msg.channel, "language_registered",
                                  dict(mention=msg.author.mention, lang=args))

    async def cmd_delete_lang(args: str, msg: discord.Message):
        if args == "":
            await send_help(msg.author)
            return

        if args.lower() not in lowerLanguages:
            await send_translated_msg(msg.channel, "language_not_found", dict(mention=msg.author.mention, lang=args))
            return

        for lang in languages:
            if lang.lower() == args.lower():
                languages.remove(lang)

        sort_file()
        await send_translated_msg(msg.channel, "language_unregistered",
                                  dict(mention=msg.author.mention, lang=args))

    # noinspection PyUnusedLocal
    async def cmd_help(args, msg: discord.Message):
        await send_help(msg.author)
        await send_translated_msg(msg.channel, "help_sent", dict(mention=msg.author.mention))

    # noinspection PyUnusedLocal
    async def cmd_del_lang_ranks(args, msg: discord.Message):
        await del_all_lang_roles(msg.server)
        await send_translated_msg(msg.channel, "all_roles_removed", dict(mention=msg.author.mention))

    add_command("+", cmd_add_lang, permissions=0x10000000)
    add_command("-", cmd_rem_lang, permissions=0x10000000)
    add_command("*", cmd_create_lang, user_permissions=0x10000000)
    add_command("/", cmd_delete_lang, user_permissions=0x10000000)
    add_command("delLangRanks", cmd_del_lang_ranks, permissions=0x10000000, user_permissions=0x10000000)
    add_command("?", cmd_help, allow_private=True)


@client.event
async def on_ready():
    print("Logged in as %s!" % client.user.name)


@client.event
async def on_message(msg: discord.Message):
    content: str = msg.content
    author: discord.Member = msg.author

    get_cmd_ret = get_command(content)

    if get_cmd_ret is None:
        return

    cmd_name, (cmd_func, allow_private, bot_perm_needed, user_perm_needed) = get_cmd_ret

    args = re.sub(r"({})\s*(.*)".format(re.escape(PREFIX + cmd_name)), r"\2", content)

    if msg.channel.is_private and not allow_private:
        await send_translated_msg(msg.channel, "private_channel", dict(mention=author.mention))
        print("Failed to execute command '{}' with args '{}' and message '{}' by user '{}' in private channel"
              .format(cmd_name, args, content, author.display_name))
        return

    if not msg.channel.is_private:
        bot_perm = msg.server.get_member(client.user.id).permissions_in(msg.channel).value
        user_perm = author.permissions_in(msg.channel).value

        if bot_perm | bot_perm_needed != bot_perm:
            await send_translated_msg(msg.channel, "bot_no_permission", dict(mention=author.mention))
            return

        if user_perm | user_perm_needed != user_perm:
            await send_translated_msg(msg.channel, "no_permission", dict(mention=author.mention))
            return

    await asyncio.coroutine(cmd_func)(args, msg)
    print("Executed command '%s' with args '%s' and message '%s' by user '%s'" % (cmd_name, args, content,
                                                                                  author.display_name))


async def send_translated_msg(channel, translation_name: str, formatting_dict: dict):
    try:
        await client.send_message(channel, get_msg_data(translation_name, default="").format(**formatting_dict))
    except discord.Forbidden:
        pass


async def add_language(lang: str, user: discord.Member) -> int:
    if lang.lower() not in lowerLanguages:
        return 1
    if has_role(user, lang):
        return 2
    if not is_role(lang, user.server):
        await create_lang(lang, user.server)
    await client.add_roles(user, get_server_role(lang, user.server))
    return 0


async def add_languages(lang_list: Set[str], user: discord.Member) -> Tuple[int, str]:
    for lang in lang_list:
        if lang.lower() not in lowerLanguages:
            return 1, lang
        if has_role(user, lang):
            return 2, lang

        if not is_role(lang, user.server):
            await create_lang(lang, user.server)

    await client.add_roles(user, *[get_server_role(lang, user.server) for lang in lang_list])
    return 0, ", ".join(lang_list)


async def rem_language(lang: str, user: discord.Member) -> int:
    if lang == '*':
        await client.remove_roles(user, *list(filter(lambda role: role.name.lower() in lowerLanguages, user.roles)))
        return 3
    if lang.lower() not in lowerLanguages:
        return 1
    if not has_role(user, lang):
        return 2
    await client.remove_roles(user, get_server_role(lang, user.server))
    return 0


async def create_lang(role: str, server: discord.Server):
    if role.lower() in lowerLanguages:
        await client.create_role(server, name=get_case_role(role), mentionable=True,
                                 permissions=discord.Permissions.none())
    if not is_role(role, server):
        print("Connection was too slow, sleep 4s")
        await asyncio.sleep(4)


def has_role(user: discord.Member, role: str):
    return role.lower() in get_string_roles(user)


def is_role(role: str, server: discord.Server):
    return role.lower() in get_server_string_roles(server)


def get_string_roles(user: discord.Member):
    return list(map(lambda role: str(role).lower(), user.roles))


def get_server_string_roles(server: discord.Server):
    return list(map(lambda role: str(role).lower(), server.roles))


def get_server_role(name: str, server: discord.Server):
    for role in server.roles:
        if role.name.lower() == name.lower():
            return role


def get_case_role(role: str):
    return languages[lowerLanguages.index(role.lower())]


async def del_all_lang_roles(server: discord.Server):
    for role in list(filter(lambda r: r.name in languages, server.roles)):
        await client.delete_role(server, role)


async def send_help(user: discord.User):
    cmd__help = ["``{}{}``".format(cmd, (" " + syntax) if syntax else "") + (" {}".format(desc) if desc else "")
                 for cmd, (syntax, desc) in commandDescriptions.items()]
    cmd__help = "\n".join(cmd__help)

    embed_data: dict = get_msg_data("help_embed")
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

        await client.send_message(user, content=None, embed=help_embed)


def get_command(msg: str):
    for cmd in commands.keys():
        if msg.startswith(PREFIX + cmd):
            return cmd, commands[cmd]

    return None


def get_msg_data(*keys: str, default=None) -> Union[dict, str, float, bool]:
    current = None
    for key in keys:
        if type(current) is dict:
            current = current.get(key, None)
        elif current is None:
            current = msg_data.get(key, None)

    return current or default


sort_file()
init_commands()
print("Loaded {} languages: {}".format(len(languages), ", ".join(languages)))
client.run("[Bot-Token]")  # TODO: Bot-Token
