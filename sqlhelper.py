import sqlite3
from typing import List


class SQLHelper:

    def __init__(self, filename: str, default_languages: List[str], default_message_language):
        self.conn = sqlite3.connect(filename)
        self.default_languages = default_languages
        self.default_msg_language = default_message_language

    def setup(self):
        self.conn.execute("CREATE TABLE IF NOT EXISTS languages (guild_id int PRIMARY KEY, topics text)")
        self.conn.execute("CREATE TABLE IF NOT EXISTS msg_language (guild_id int PRIMARY KEY, language text)")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def is_guild(self, guild_id: int) -> bool:
        return bool(self.conn.execute("SELECT guild_id FROM languages WHERE guild_id=?", (guild_id,)).fetchone())

    def add_guild(self, guild_id: int):
        self.conn.execute("INSERT INTO languages VALUES (?, ?)", (guild_id, "\n".join(self.default_languages)))
        self.conn.execute("INSERT INTO msg_language VALUES (?, ?)", (guild_id, self.default_msg_language))

    def get_guild_count(self):
        return self.conn.execute("SELECT COUNT(*) FROM languages").fetchone()[0]

    def get_topics(self, guild_id: int) -> List[str]:
        result = self.conn.execute("SELECT topics FROM languages WHERE guild_id=?", (guild_id,)).fetchone()
        return result[0].strip().split("\n") if result and result[0].strip().split("\n")[0] else list()

    def add_topic(self, guild_id: int, topic: str) -> bool:
        if not self.conn.execute("SELECT guild_id FROM languages WHERE guild_id=?", (guild_id,)):
            self.add_guild(guild_id)

        before = self.get_topics(guild_id)
        if topic in before:
            return False

        before.append(topic)
        self.conn.execute("UPDATE languages SET topics=? WHERE guild_id=?", ("\n".join(before), guild_id))
        return True

    def remove_topic(self, guild_id: int, topic: str):
        before = {lang.lower(): lang for lang in self.get_topics(guild_id)}
        if not before or topic.lower() not in before:
            return False

        del before[topic.lower()]
        self.conn.execute("UPDATE languages SET topics=? WHERE guild_id=?", ("\n".join(before.values()), guild_id))
        return True

    def get_msg_language(self, guild_id: int):
        if not self.is_guild(guild_id):
            self.add_guild(guild_id)
        return self.conn.execute("SELECT language FROM msg_language WHERE guild_id=?", (guild_id,)).fetchone()[0]

    def set_message_language(self, guild_id: int, language: str):
        if not self.is_guild(guild_id):
            self.add_guild(guild_id)
        self.conn.execute("UPDATE msg_language SET language=? WHERE guild_id=?", (language, guild_id))

    def commit(self):
        self.conn.commit()

    def close(self):
        self.commit()
        self.conn.close()
