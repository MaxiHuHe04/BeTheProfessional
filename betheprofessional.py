import discord
import asyncio
import json
import re

client = discord.Client()

MSG_LANG = "de-DE"

with open("languages", mode='r') as langFile:
    languages = langFile.readlines()

with open("lang/%s.json" % MSG_LANG, mode='r', encoding="utf-8") as msgLangFile:
    msg_data = json.load(msgLangFile)

languages = [x.strip() for x in languages]
lowerLanguages = list(map(lambda lang: lang.lower(), languages))


def sort_file():
    with open("languages", mode="w") as lang_file:
        for l in sorted(languages):
            lang_file.write(l + "\n")


@client.event
async def on_ready():
    print("Logged in as %s!" % client.user.name)


@client.event
async def on_message(msg: discord.Message):
    content: str = msg.content
    author: discord.Member = msg.author

    async def send_translated_msg(translation_name: str, formatting_dict: dict):
        await client.send_message(msg.channel, msg_data[translation_name].format(**formatting_dict))

    if not msg.server.get_member(client.user.id).permissions_in(msg.channel).manage_roles:
        send_translated_msg("bot_no_permission", dict(mention=author.mention))
        return

    if content.startswith(".+"):
        lang = re.sub(r"\s*(\w+)", r"\1", content[2:].lower())

        if lang != "":
            err = await add_language(lang, author)
            formatting = {"lang": lang, "mention": msg.author.mention}

            if err == 0:
                await send_translated_msg("language_added", formatting)
            elif err == 1:
                await send_translated_msg("language_not_found", formatting)
            elif err == 2:
                await send_translated_msg("user_has_language_already", formatting)

    elif content.startswith(".-"):
        lang = re.sub(r"\s*(\w+)", r"\1", content[2:].lower())

        if lang != "":
            err = await rem_language(lang, author)
            formatting = {"lang": lang, "mention": msg.author.mention}

            if err == 0:
                await send_translated_msg("language_removed", formatting)
            elif err == 1:
                await send_translated_msg("language_not_existing", formatting)
            elif err == 2:
                await send_translated_msg("language_not_yet_requested", formatting)
            elif err == 3:
                await send_translated_msg("all_languages_removed", formatting)

    elif content.lower().startswith(".dellangranks"):
        perms: discord.Permissions = author.permissions_in(msg.channel)
        if perms.manage_roles:
            await del_all_lang_roles(msg.server)
            await send_translated_msg("all_roles_removed", dict(mention=author.mention))
        else:
            await send_translated_msg("no_permission", dict(mention=author.mention))


async def add_language(lang: str, user: discord.Member) -> int:
    if lang.lower() not in lowerLanguages:
        return 1
    if has_role(user, lang):
        return 2
    if not is_role(lang, user.server):
        await create_lang(lang, user.server)
    await client.add_roles(user, get_server_role(lang, user.server))
    return 0


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
        print("Connection was too slow, sleep 5s")
        await asyncio.sleep(5)


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

sort_file()
print("Loaded %i languages: " % len(languages) + ", ".join(languages))
client.run("MzQ5MjIyODY3MzQ0NDI0OTcw.DHyYJQ.GW_oVsjEo4FKFsMbDWJTHto1Y-M")
