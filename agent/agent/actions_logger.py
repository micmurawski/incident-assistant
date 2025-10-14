from dataclasses import dataclass, field

from agent.telemetry_service import get_telemetry_service

logging = get_telemetry_service()


@dataclass(frozen=True)
class ActionLog:
    caller: str
    function_name: str
    params: dict = field(default_factory=dict)
    error: str | Exception

    def to_txt(self) -> str:
        line = f"{self.caller} called {self.function_name} with {str(self.params)}"
        if self.error:
            line += f" with error {str(self.error)}"
        return line


class ActionsLogger:
    _instances = []

    def __init__(self, name: str):
        self.name = name
        self.logs: list[ActionLog] = []

    @classmethod
    def get_instance(cls, name):
        if name not in cls._instances:
            cls._instances[name] = cls(name)
        return cls._instances[name]

    def log_action(self, caller: str, function: str, params: dict, error: str | Exception):
        action = ActionLog(caller, function, params, error)
        self.logs.append(action)
        logging.info(action.to_txt)
