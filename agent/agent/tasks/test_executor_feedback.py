import io

import pytest

from agent.llm import AgentRegistry
from agent.settings import SettingsManager
from agent.tasks.executor import TaskExecutor
from agent.tasks.tasks import Task
from agent.tasks.types import TaskStatus


@pytest.fixture(autouse=True)
def _noop_session_store(monkeypatch):
    monkeypatch.setattr(
        "agent.tasks.executor.upsert_session_messages",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "agent.tasks.executor.fetch_session_messages",
        lambda *a, **k: [],
    )


class _FakeAssigneeAgent:
    class _ApiHandler:
        provider = "anthropic"

    api_handler = _ApiHandler()

    def __init__(self, response_texts: str | list[str]):
        if isinstance(response_texts, str):
            self._responses = [response_texts]
        else:
            self._responses = list(response_texts)
        self.call_count = 0

    async def call(self, shared):
        idx = min(self.call_count, len(self._responses) - 1)
        text = self._responses[idx]
        self.call_count += 1
        shared["messages"].append({"role": "assistant", "content": text})

    def get_shared(self):
        return {}


class _FakeFeedbackIterator:
    def __init__(self, tool_use):
        self.tool_use = tool_use
        self.usage_summary = {}

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class _FakeAssignerAgent:
    def __init__(self, tool_use_sequences):
        self._tool_use_sequences = list(tool_use_sequences)

    async def create_message(self, **kwargs):
        tool_use = self._tool_use_sequences.pop(0)
        return _FakeFeedbackIterator(tool_use)


class _FakeFeedbackTools:
    def tools_definitions(self, **kwargs):
        return []


class _NamedStringIO(io.StringIO):
    def __init__(self, name: str):
        super().__init__()
        self.name = name

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_feedback_retry_second_attempt_approves(monkeypatch):
    settings = SettingsManager.get_instance()
    settings.set("features.feedback_enabled", True)

    parent = Task(
        assignee="manager",
        assigner="human",
        conversation=[{"role": "user", "content": "root task"}],
        messages_history=[{"role": "user", "content": "root task"}],
    )

    assignee_agent = _FakeAssigneeAgent("candidate report")
    assigner_agent = _FakeAssignerAgent(
        tool_use_sequences=[
            [],
            [{"name": "provide_feedback", "input": {"approve": True}}],
        ]
    )

    registry = AgentRegistry.get_instance()
    registry.agents = {"worker": assignee_agent, "manager": assigner_agent}

    monkeypatch.setattr(Task, "save", lambda self, key=None: None)
    dumped = {}

    def fake_open(path, mode="r", *args, **kwargs):
        return _NamedStringIO(path)

    def fake_dump(obj, fp, *args, **kwargs):
        if hasattr(fp, "name"):
            dumped[fp.name] = obj
        else:
            dumped["unknown"] = obj

    import agent.tasks.executor as executor_module

    monkeypatch.setattr(executor_module, "open", fake_open, raising=False)
    monkeypatch.setattr(executor_module.json, "dump", fake_dump)

    result = await TaskExecutor.assign_and_run(
        parent_task=parent,
        assigner="manager",
        assignee="worker",
        message="do work",
        todos_str="[ ] one task",
        feedback_tools=_FakeFeedbackTools(),
        depth=0,
        session_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    )

    assert result.error is None
    child = parent.children[0]
    assistant_messages = [m for m in child.conversation if m.get("role") == "assistant"]
    assert len(assistant_messages) == 1
    assert assistant_messages[0]["content"] == "candidate report"
    assert "debug_feedback_messages.json" in dumped


@pytest.mark.asyncio
async def test_approve_feedback_message_not_duplicated(monkeypatch):
    settings = SettingsManager.get_instance()
    settings.set("features.feedback_enabled", True)

    parent = Task(
        assignee="manager",
        assigner="human",
        conversation=[{"role": "user", "content": "root task"}],
        messages_history=[{"role": "user", "content": "root task"}],
    )

    assignee_agent = _FakeAssigneeAgent("candidate report")
    feedback_text = "Task completed successfully."
    assigner_agent = _FakeAssignerAgent(
        tool_use_sequences=[
            [{"name": "provide_feedback", "input": {"approve": True, "feedback": feedback_text}}],
        ]
    )

    registry = AgentRegistry.get_instance()
    registry.agents = {"worker": assignee_agent, "manager": assigner_agent}
    monkeypatch.setattr(Task, "save", lambda self, key=None: None)

    monkeypatch.setattr("agent.tasks.executor.open", lambda *a, **k: _NamedStringIO("debug"))
    monkeypatch.setattr("agent.tasks.executor.json.dump", lambda *a, **k: None)

    result = await TaskExecutor.assign_and_run(
        parent_task=parent,
        assigner="manager",
        assignee="worker",
        message="do work",
        todos_str="[ ] one task",
        feedback_tools=_FakeFeedbackTools(),
        depth=0,
        session_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    )

    assert result.error is None
    child = parent.children[0]
    feedback_msgs = [m for m in child.messages_history if m.get("role") == "user" and m.get("content") == feedback_text]
    assert len(feedback_msgs) == 1


@pytest.mark.asyncio
async def test_feedback_path_respects_disabled_setting(monkeypatch):
    settings = SettingsManager.get_instance()
    settings.set("features.feedback_enabled", False)

    parent = Task(
        assignee="manager",
        assigner="human",
        conversation=[{"role": "user", "content": "root task"}],
        messages_history=[{"role": "user", "content": "root task"}],
    )

    assignee_agent = _FakeAssigneeAgent("final worker answer")
    assigner_agent = _FakeAssignerAgent(tool_use_sequences=[])

    registry = AgentRegistry.get_instance()
    registry.agents = {"worker": assignee_agent, "manager": assigner_agent}

    monkeypatch.setattr(Task, "save", lambda self, key=None: None)

    result = await TaskExecutor.assign_and_run(
        parent_task=parent,
        assigner="manager",
        assignee="worker",
        message="do work",
        todos_str="[ ] one task",
        feedback_tools=_FakeFeedbackTools(),
        depth=0,
        session_id="cccccccc-cccc-cccc-cccc-cccccccccccc",
    )

    assert result.error is None
    child = parent.children[0]
    assert child.status == TaskStatus.DONE
    assert child.conversation[-1]["content"] == "final worker answer"
    assert result.result == "final worker answer\n\nsession_id: cccccccc-cccc-cccc-cccc-cccccccccccc"


def test_result_with_session_id_string():
    assert TaskExecutor._result_with_session_id("hello", "abc-uuid") == "hello\n\nsession_id: abc-uuid"


def test_result_with_session_id_dict():
    out = TaskExecutor._result_with_session_id({"feedback": "x"}, "sid-1")
    assert out["feedback"] == "x"
    assert out["session_id"] == "sid-1"


def test_result_with_session_id_list_block():
    out = TaskExecutor._result_with_session_id([{"type": "text", "text": "hi"}], "sid-2")
    assert out[0]["text"] == "hi"
    assert out[-1]["type"] == "text"
    assert "session_id: sid-2" in out[-1]["text"]


def test_normalize_session_id_line_format():
    raw = "session_id: AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA"
    assert TaskExecutor._normalize_session_id(raw) == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def test_normalize_session_id_embedded_in_text():
    raw = "Use this id to continue.\n\nsession_id: `BBBBBBBB-BBBB-BBBB-BBBB-BBBBBBBBBBBB`"
    assert TaskExecutor._normalize_session_id(raw) == "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


@pytest.mark.asyncio
async def test_session_messages_prepended_before_new_task(monkeypatch):
    settings = SettingsManager.get_instance()
    settings.set("features.feedback_enabled", False)

    prior = [{"role": "user", "content": "prior from session"}]

    def fake_fetch(assigner, assignee, sid):
        if sid == "dddddddd-dddd-dddd-dddd-dddddddddddd":
            return prior
        return None

    monkeypatch.setattr("agent.tasks.executor.fetch_session_messages", fake_fetch)

    parent = Task(
        assignee="manager",
        assigner="human",
        conversation=[{"role": "user", "content": "root task"}],
        messages_history=[{"role": "user", "content": "root task"}],
    )

    assignee_agent = _FakeAssigneeAgent("reply")
    registry = AgentRegistry.get_instance()
    registry.agents = {"worker": assignee_agent, "manager": _FakeAssignerAgent([])}

    monkeypatch.setattr(Task, "save", lambda self, key=None: None)

    await TaskExecutor.assign_and_run(
        parent_task=parent,
        assigner="manager",
        assignee="worker",
        message="new task",
        todos_str="[ ] step",
        feedback_tools=_FakeFeedbackTools(),
        depth=0,
        session_id="dddddddd-dddd-dddd-dddd-dddddddddddd",
    )

    child = parent.children[0]
    assert child.conversation[0] == prior[0]
    assert "new task" in child.conversation[1]["content"]
    assert "Here is the todo list:" in child.conversation[1]["content"]
    assert "[ ] step" in child.conversation[1]["content"]


@pytest.mark.asyncio
async def test_prefixed_session_id_is_normalized_for_lookup(monkeypatch):
    settings = SettingsManager.get_instance()
    settings.set("features.feedback_enabled", False)

    expected_sid = "dddddddd-dddd-dddd-dddd-dddddddddddd"
    prior = [{"role": "user", "content": "prior from session"}]
    seen = {}

    def fake_fetch(assigner, assignee, sid):
        seen["sid"] = sid
        if sid == expected_sid:
            return prior
        return None

    monkeypatch.setattr("agent.tasks.executor.fetch_session_messages", fake_fetch)

    parent = Task(
        assignee="manager",
        assigner="human",
        conversation=[{"role": "user", "content": "root task"}],
        messages_history=[{"role": "user", "content": "root task"}],
    )

    assignee_agent = _FakeAssigneeAgent("reply")
    registry = AgentRegistry.get_instance()
    registry.agents = {"worker": assignee_agent, "manager": _FakeAssignerAgent([])}
    monkeypatch.setattr(Task, "save", lambda self, key=None: None)

    result = await TaskExecutor.assign_and_run(
        parent_task=parent,
        assigner="manager",
        assignee="worker",
        message="new task",
        todos_str="[ ] step",
        feedback_tools=_FakeFeedbackTools(),
        depth=0,
        session_id=f"session_id: {expected_sid}",
    )

    assert result.error is None
    assert seen["sid"] == expected_sid
    child = parent.children[0]
    assert child.conversation[0] == prior[0]


@pytest.mark.asyncio
async def test_explicit_session_id_missing_returns_error(monkeypatch):
    settings = SettingsManager.get_instance()
    settings.set("features.feedback_enabled", False)

    monkeypatch.setattr("agent.tasks.executor.fetch_session_messages", lambda *a, **k: None)
    monkeypatch.setattr("agent.tasks.executor.upsert_session_messages", lambda *a, **k: None)

    parent = Task(
        assignee="manager",
        assigner="human",
        conversation=[{"role": "user", "content": "root"}],
        messages_history=[{"role": "user", "content": "root"}],
    )
    registry = AgentRegistry.get_instance()
    registry.agents = {"worker": _FakeAssigneeAgent("x"), "manager": _FakeAssignerAgent([])}
    monkeypatch.setattr(Task, "save", lambda self, key=None: None)

    result = await TaskExecutor.assign_and_run(
        parent_task=parent,
        assigner="manager",
        assignee="worker",
        message="task",
        todos_str="[ ] t",
        feedback_tools=_FakeFeedbackTools(),
        depth=0,
        session_id="00000000-0000-0000-0000-000000000001",
    )

    assert result.result is None
    assert result.error is not None
    assert "No session found" in result.error
    assert "00000000-0000-0000-0000-000000000001" in result.error
    assert len(parent.children) == 0
