from typing import Literal, TypedDict

from peewee import SqliteDatabase

DatabaseDriver = Literal["sqlite"]


class PersistenceSettings(TypedDict, total=False):
    database_driver: DatabaseDriver
    database_url: str


DEFAULT_PERSISTENCE_SETTINGS: PersistenceSettings = {
    "database_driver": "sqlite",
    "database_url": "./agent.db",
}


def init_db(settings: PersistenceSettings = DEFAULT_PERSISTENCE_SETTINGS) -> SqliteDatabase:
    database = SqliteDatabase(settings["url"])
    from agent.persistence.model import (Agent, Conversation, Message, Session,
                                         Task)
    models = [Session, Task, Message, Agent, Conversation]
    for model in models:
        model.bind(database)
    database.connect()
    database.create_tables(models)
