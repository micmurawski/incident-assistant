from typing import Literal, TypedDict

from peewee import SqliteDatabase

DatabaseDriver = Literal["sqlite"]


class PersistenceSettings(TypedDict, total=False):
    database_driver: DatabaseDriver
    database_url: str


DEFAULT_PERSISTENCE_SETTINGS: PersistenceSettings = {
    "driver": "sqlite",
    "url": "./agent.db",
}


def init_db() -> SqliteDatabase:
    from agent.persistence.model import TaskModel
    from agent.settings import SettingsManager
    settings = SettingsManager.get_instance()
    database_settings = settings.get("persistence") or DEFAULT_PERSISTENCE_SETTINGS
    database = SqliteDatabase(database_settings["url"])
    models = [TaskModel]
    for model in models:
        model.bind(database)
    database.connect()
    database.create_tables(models, safe=True)
    return database


if __name__ == "__main__":
    init_db()