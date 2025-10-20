import os
from datetime import datetime
from uuid import uuid4

from peewee import (
    BooleanField,
    CharField,
    DateTimeField,
    DoesNotExist,
    ForeignKeyField,
    IntegerField,
    Model,
    SqliteDatabase,
    TextField,
    UUIDField,
    ValuesList,
)

from .settings import DEFAULT_PERSISTENCE_SETTINGS, PersistenceSettings

db = SqliteDatabase("./agent.db")


class Session(Model):
    id = CharField(primary_key=True, default=lambda: str(uuid4()))
    created_at = DateTimeField(default=lambda: datetime.now())
    updated_at = DateTimeField(default=lambda: datetime.now())

    class Meta:
        database = db
        table_name = "sessions"


class Task(Model):
    id = CharField(primary_key=True, default=lambda: str(uuid4()))
    session = ForeignKeyField(Session, backref="tasks", null=True)
    assignee = CharField(null=True)
    assigner = CharField(null=True)
    created_at = DateTimeField(default=lambda: datetime.now())
    updated_at = DateTimeField(default=lambda: datetime.now())
    todo_list = TextField(null=True)
    parent = ForeignKeyField("self", backref="tasks", null=True)  # type: ignore
    children = ValuesList(CharField)  # type: ignore
    root = ForeignKeyField("self", backref="tasks", null=True)  # type: ignore
    status = CharField(default="awaiting_input")
    tool_usage = TextField(null=True)
    conversation = TextField(null=True)

    class Meta:
        database = db
        table_name = "tasks"

    def get_all_children(self) -> list["Task"]:
        return Task.select().where(Task.parent == self.id)

    @classmethod
    def create_or_update(cls, **kwargs):
        _id = kwargs.pop("id")
        try:
            selected = cls.select().where(cls.id == _id).get()
            for key, value in kwargs.items():
                setattr(selected, key, value)
            selected.save()
        except DoesNotExist:
            cls.create(id=_id, **kwargs)


class Message(Model):
    id = UUIDField(primary_key=True, default=lambda: str(uuid4()))
    task = ForeignKeyField(Task, backref="messages", null=True)
    session = ForeignKeyField(Session, backref="messages", null=True)
    created_at = DateTimeField(default=lambda: datetime.now())
    updated_at = DateTimeField(default=lambda: datetime.now())

    role = CharField()
    content = TextField(default=None)
    ts = IntegerField(default=lambda: datetime.now().timestamp())
    is_summary = BooleanField(default=False)

    class Meta:
        database = db
        table_name = "messages"


def persist_message(message: Message, session_id: str, task_id: str = None):
    message = Message.create(
        session=session_id,
        task=task_id,
        id=message.get("id", str(uuid4())),
        role=message["role"],
        content=message["content"],
        ts=message["ts"],
        is_summary=message["is_summary"],
    )
    message.save()


def create_tables(db: SqliteDatabase):
    db.create_tables([Session, Task, Message])


def init_db(settings: PersistenceSettings = DEFAULT_PERSISTENCE_SETTINGS) -> SqliteDatabase:
    db = SqliteDatabase(settings["database_url"])
    db.connect()
    create_tables(db)
    return db
