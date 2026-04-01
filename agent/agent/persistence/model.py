from datetime import datetime

from peewee import (CharField, CompositeKey, DateTimeField, IntegerField,
                    Model, TextField)

from agent.tasks.types import TaskStatus


class TaskModel(Model):
    root_id = CharField()
    id = CharField()
    status = CharField(choices=[status.value for status in TaskStatus])
    todo_list = TextField()
    children = TextField()
    parent = TextField()
    root = TextField()
    assignee = TextField()
    assigner = TextField()
    usage = TextField(default="{}")
    total_usage = TextField(default="{}")
    iterations_count = IntegerField(default=0)
    iterations_limit = IntegerField(default=20)
    conversation = TextField()
    messages_history = TextField()
    last_message_ts = IntegerField()
    created_at = DateTimeField(default=datetime.now)
    updated_at = DateTimeField(default=datetime.now)

    class Meta:
        table_name = "tasks"
        primary_key = CompositeKey("root_id", "id")


class SessionMessagesModel(Model):
    """Snapshot of shared messages for an assign_task session."""

    assigner = CharField()
    assignee = CharField()
    session_id = CharField()
    messages_json = TextField()
    created_at = DateTimeField(default=datetime.now)
    updated_at = DateTimeField(default=datetime.now)

    class Meta:
        table_name = "session_messages"
        primary_key = CompositeKey("assigner", "assignee", "session_id")
