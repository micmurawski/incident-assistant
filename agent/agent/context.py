import os
from dataclasses import dataclass

from agent.code_index.code_index_manager import CodeIndexManager
from agent.file_ops import FileOpsManager
from agent.providers import build_api_handler
from agent.providers.base import ApiHandler
from agent.settings import SettingsManager


@dataclass
class Context:
    file_ops_manager: FileOpsManager
    code_index_manager: CodeIndexManager
    api_handler: ApiHandler

    def __init__(self):
        settings = SettingsManager.get_instance()
        cwd = settings.get("workspace.path") or os.getcwd()
        self.file_ops_manager = FileOpsManager(cwd=cwd)
        self.code_index_manager = CodeIndexManager.get_instance(cwd)
        self.api_handler = build_api_handler(**settings.get("api"))

    @property
    def cwd(self) -> str:
        return self.file_ops_manager.cwd

    @property
    def settings_manager(self) -> SettingsManager:
        return SettingsManager.get_instance()
