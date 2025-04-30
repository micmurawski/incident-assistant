from typing import List, Dict, Any, TypeVar
from langchain_core.messages import BaseMessage, HumanMessage
from dataclasses import dataclass, field
import uuid
from enum import Enum
from sme_agent.message_serialization import serialize_messages, deserialize_messages
MAX_NUMBER_OF_FEEDBACK_MESSAGES = 5


T = TypeVar('T', bound='Task')


class TaskStatus(str, Enum):
    AWAITING_INPUT = "awaiting_input"
    AWAITING_REVIEW = "awaiting_review"
    DONE = "done"
    DISCARDED = "discarded"


@dataclass
class Task:
    name: str
    description: str
    assigner: str
    assignee: str
    depends_on: List[T] = field(default_factory=list)
    summarized_output: BaseMessage | None = None
    discussion: List[BaseMessage] = field(default_factory=list)
    status: TaskStatus = field(default=TaskStatus.AWAITING_INPUT)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "assigner": self.assigner,
            "assignee": self.assignee,
            "depends_on": [dep.to_dict() for dep in self.depends_on],
            "summarized_output": serialize_messages(self.summarized_output) if self.summarized_output else None,
            "discussion": serialize_messages(self.discussion),
            "status": self.status.value,
            "id": self.id
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> T:
        self = cls(
            name=data["name"],
            description=data["description"],
            assigner=data["assigner"],
            assignee=data["assignee"],
            depends_on=[Task.from_dict(dep) for dep in data["depends_on"]],
            id=data["id"],
            status=TaskStatus(data["status"])
        )
        self.summarized_output = deserialize_messages(data["summarized_output"]) if data["summarized_output"] else None
        self.discussion = deserialize_messages(data["discussion"])
        
        return self

    def create_dependent_task(self, name: str, description: str, assignee: str, assigner: str | None = None):
        if assigner is None:
            assigner = self.assigner
        task = Task(name, description, assigner, assignee)
        self.depends_on.append(task)
        return task

    def __repr__(self):
        return f'Task(name={self.name}, assigner="{self.assigner}", assignee="{self.assignee}", status={self.status})'

    def is_done(self) -> bool:
        return self.status == TaskStatus.DONE

    def is_discarded(self) -> bool:
        return self.status == TaskStatus.DISCARDED

    def is_awaiting_input(self) -> bool:
        return self.status == TaskStatus.AWAITING_INPUT

    def is_awaiting_review(self) -> bool:
        return self.status == TaskStatus.AWAITING_REVIEW

    def move_to_done(self, raise_if_not_done: bool = True) -> bool:
        if all(task.is_done() for task in self.depends_on if not task.is_discarded()):
            self.status = TaskStatus.DONE
            return True
        if raise_if_not_done:
            raise ValueError(
                "Task is not done. It still has dependencies that are not done.")
        return False

    def add_input(self, message: BaseMessage):
        if self.status != TaskStatus.AWAITING_INPUT:
            raise ValueError("Task is not awaiting input")
        message.name = self.assignee
        self.status = TaskStatus.AWAITING_REVIEW
        self.discussion.append(message)

    def review(self, message: BaseMessage):
        if self.status != TaskStatus.AWAITING_REVIEW:
            raise ValueError("Task is not awaiting review")

        if len(self.discussion) >= 2*MAX_NUMBER_OF_FEEDBACK_MESSAGES:
            raise ValueError("Task has too many feedback messages")

        message.name = self.assigner
        self.status = TaskStatus.AWAITING_INPUT
        self.discussion.append(message)

    def discard(self):
        self.status = TaskStatus.DISCARDED
        self.remove_all_discarded()

    def remove_all_discarded(self):
        root = [self]
        while root:
            task = root.pop()
            task.depends_on = [
                dep for dep in task.depends_on if not dep.is_discarded]
            root.extend(task.depends_on)

    def find_by_name(self, name: str) -> list[T]:
        root = [self]
        res = []
        while root:
            task = root.pop()
            if task.name == name:
                res.append(task)
            root.extend(task.depends_on)
        return res

    def get_dependency_sorted_tasks_for_assignee(self, assignee: str, only_unblocked: bool = True) -> list[T]:
        res = []
        root = [self]
        while root:
            task = root.pop()
            if task.assignee == assignee and not task.is_done() and not task.is_discarded():
                if only_unblocked:
                    if not task.depends_on:
                        res.append(task)
                else:
                    res.append(task)
            root.extend(task.depends_on)
        return res

    def get_all_tasks_with_status(self, status: TaskStatus, assignee: str | None = None) -> list[T]:
        res = []
        root = [self]
        while root:
            task = root.pop()

            status_correct = task.status == status
            assignee_correct = assignee is None or task.assignee == assignee
            depends_on_done = all(dep.is_done()
                                  for dep in task.depends_on if not dep.is_discarded())

            if status_correct and assignee_correct and depends_on_done:
                res.append(task)
            root.extend(task.depends_on)
        return res


if __name__ == "__main__":
    # todo_list = TasksCollection()
    goal = Task(
        name="Become blog writer",
        description="Become a blog writer",
        assigner="Agent Blog Writer",
        assignee="Agent Blog Writer"
    )

    task1 = goal.create_dependent_task(
        name="Create a blog site",
        description="Create a blog site",
        assignee="Agent Web Developer"
    )
    task_0 = goal.create_dependent_task(
        name="Think about the blog topic",
        description="Think about the blog topic",
        assignee="Agent Blog Writer"
    )
    task2 = goal.create_dependent_task(
        name="Write a blog post",
        description="Write a blog post about the benefits of using AI",
        assignee="Agent Blog Writer"
    )
    task3 = task2.create_dependent_task(
        name="Advertise the blog site",
        description="Advertise the blog site",
        assignee="Agent Marketer"
    )
    task4 = task2.create_dependent_task(
        name="Write a blog post about the benefits of using AI",
        description="Write a blog post about the benefits of using AI",
        assignee="Agent Blog Writer"
    )
    task4.create_dependent_task(
        name="Organize events",
        description="Organize events",
        assignee="Agent Event Organizer"
    )
    import json
    goal.add_input(HumanMessage(name="Bob", content="I have thought about the blog topic",))
    data = goal.to_dict()
    goal = Task.from_dict(data)
    print(json.dumps(goal.to_dict(), indent=4))