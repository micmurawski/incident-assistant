from datetime import datetime

from peewee import (CharField, CompositeKey, DateTimeField, IntegerField,
                    Model, TextField)

from agent.tasks.types import TaskStatus


class ConversationModel(Model):
    hash_key = CharField()
    sort_key = IntegerField()
    content = TextField()
    created_at = DateTimeField(default=datetime.now)
    updated_at = DateTimeField(default=datetime.now)

    class Meta:
        table_name = "conversations"
        primary_key = CompositeKey("hash_key", "sort_key")


class TaskModel(Model):
    root_id = CharField()
    id = CharField()
    conversation_content = TextField()
    status = CharField(choices=[status.value for status in TaskStatus])
    todo_list = TextField()
    children = TextField()
    parent = TextField()
    root = TextField()
    assignee = TextField()
    assigner = TextField()
    conversation = TextField()
    last_message_ts = IntegerField()
    created_at = DateTimeField(default=datetime.now)
    updated_at = DateTimeField(default=datetime.now)

    class Meta:
        table_name = "tasks"
        primary_key = CompositeKey("root_id", "id")

