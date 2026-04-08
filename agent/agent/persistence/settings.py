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
    from agent.persistence.model import SessionMessagesModel, TaskModel
    from agent.settings import SettingsManager
    settings = SettingsManager.get_instance()
    database_settings = settings.get("persistence") or DEFAULT_PERSISTENCE_SETTINGS
    database = SqliteDatabase(database_settings["url"])
    models = [TaskModel, SessionMessagesModel]
    for model in models:
        model.bind(database)
    database.connect()
    database.create_tables(models, safe=True)
    #_migrate_tasks_resolved_at(database)
    return database


def _migrate_tasks_resolved_at(database: SqliteDatabase) -> None:
    """Add ``resolved_at`` if missing; backfill DONE rows with ``updated_at``."""
    cursor = database.execute_sql("PRAGMA table_info(tasks)")
    columns = {row[1] for row in cursor.fetchall()}
    if "resolved_at" not in columns:
        database.execute_sql(
            "ALTER TABLE tasks ADD COLUMN resolved_at DATETIME NULL"
        )
    database.execute_sql(
        """
        UPDATE tasks
        SET resolved_at = updated_at
        WHERE resolved_at IS NULL AND status = 'DONE'
        """
    )


if __name__ == "__main__":
    init_db()