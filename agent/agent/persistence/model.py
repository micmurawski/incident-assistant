from datetime import datetime
from uuid import uuid4
import json
from peewee import (BooleanField, CharField, DateTimeField, DoesNotExist,
                    ForeignKeyField, IntegerField, Model,
                    TextField, ValuesList, CompositeKey)


class CreateOrUpdateMixin:
    @classmethod
    def create_or_update(cls, **kwargs):
        _id = kwargs.pop("id")
        try:
            selected = cls.select().where(cls.id == _id).get()
            for key, value in kwargs.items():
                setattr(selected, key, value)
            selected.save()
        except DoesNotExist:
            cls.create(**kwargs)


class GlobalTicker:
    _global_ticker = 1

    @classmethod
    def increment(cls):
        cls._global_ticker += 1
        return cls._global_ticker

    @classmethod
    def get_global_ticker(cls):
        return cls._global_ticker


class Session(Model):
    id = CharField(primary_key=True, default=lambda: str(uuid4()))
    created_at = DateTimeField(default=lambda: datetime.now())
    updated_at = DateTimeField(default=lambda: datetime.now())

    class Meta:
        table_name = "sessions"


class Agent(Model, CreateOrUpdateMixin):
    id = CharField(primary_key=True, default=lambda: str(uuid4()))
    name = CharField()
    description = TextField()

    class Meta:
        table_name = "agents"


class Task(Model, CreateOrUpdateMixin):
    id = CharField(primary_key=True, default=lambda: str(uuid4()))
    session = ForeignKeyField(Session, backref="tasks", null=True)
    assignee = CharField(null=True)
    assigner = CharField(null=True)
    created_at = DateTimeField(default=lambda: datetime.now())
    updated_at = DateTimeField(default=lambda: datetime.now())
    todo_list = TextField(null=True)
    parent = ForeignKeyField("self", backref="tasks",
                             null=True)  # type: ignore
    root = ForeignKeyField("self", backref="tasks", null=True)  # type: ignore
    status = CharField(default="awaiting_input")
    tool_usage = TextField(null=True)

    class Meta:
        table_name = "tasks"

    @property
    def children(self) -> list["Task"]:
        return Task.select().where(Task.parent == self.id).all()


class Conversation(Model, CreateOrUpdateMixin):
    id = CharField(default=lambda: str(uuid4()))
    version = IntegerField(default=1)
    task = ForeignKeyField(Task, backref="conversations", null=True)
    created_at = DateTimeField(default=lambda: datetime.now())
    updated_at = DateTimeField(default=lambda: datetime.now())
    participants = TextField(null=True)  # Store as JSON string; parse to/from list in application logic

    class Meta:
        table_name = "conversations"
        primary_key = CompositeKey('id', 'version')

    @property
    def messages(self) -> list["Message"]:
        return Message.select().where(Message.conversation_id == self.id, Message.conversation_version == self.version)


class Message(Model):
    id = CharField(default=lambda: str(uuid4()))
    type = CharField()
    role = CharField()
    content = TextField(default=None)
    ts = IntegerField(default=lambda: datetime.now().timestamp())
    is_summary = BooleanField(default=False)
    global_ticker = IntegerField(default=GlobalTicker.get_global_ticker())

    task = ForeignKeyField(Task, backref="messages", null=True)
    session = ForeignKeyField(Session, backref="messages", null=True)
    agent = ForeignKeyField(Agent, backref="messages", null=True)
    conversation_id = CharField(null=True)
    conversation_version = IntegerField(null=True)

    class Meta:
        table_name = "messages"
        primary_key = CompositeKey('id', 'type')


class MemoryService:
    @classmethod
    def upsert_conversation(cls, **kwargs):
        kwargs["participants"] = json.dumps(kwargs.pop("participants", []))
        Conversation.create_or_update(**kwargs)

    @classmethod
    def get_latest_conversation(cls, conversation_id: str) -> Conversation:
        conversation = Conversation.select().where(Conversation.id == conversation_id).order_by(Conversation.version.desc()).get()
        return conversation.messages

    @classmethod
    def save_message(
        cls,
        message: dict,
        task_id: str | None = None,
        session_id: str | None = None,
        agent_id: str | None = None,
        conversation_id: str | None = None,
        conversation_version: int | None = None,
        **kwargs
    ):
        ts = int(datetime.now().timestamp())
        id = message.get("id") or kwargs.pop("id") or str(uuid4())
        is_summary = message.get("is_summary") or kwargs.pop(
            "is_summary", None) or False

        _type = message.get("type", "text")

        if _type in {"tool_use", "tool_result"}:
            content = json.dumps(message.get("content"))
        else:
            content = message.get("content")

        Message.create(
            id=id,
            role=message["role"],
            type=_type,
            content=content,
            is_summary=is_summary,
            ts=ts,
            task=task_id,
            session=session_id,
            agent=agent_id,
            conversation_id=conversation_id,
            conversation_version=conversation_version,
        )

    @classmethod
    def upsert_agent(cls, **kwargs):
        Agent.create_or_update(**kwargs)
