from typing import Literal, TypedDict

DatabaseDriver = Literal["sqlite"]


class PersistenceSettings(TypedDict, total=False):
    database_driver: DatabaseDriver
    database_url: str


DEFAULT_PERSISTENCE_SETTINGS: PersistenceSettings = {
    "database_driver": "sqlite",
    "database_url": "./agent.db",
}
