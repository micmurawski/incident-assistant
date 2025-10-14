from agent.telemetry_service import get_telemetry_service

logging = get_telemetry_service()


class CheckpointService:
    def __init__(self, checkpoints_dir: str) -> None:
        self.checkpoints_dir = checkpoints_dir
        self._checkpoints = []
        self._base_hash = None
        self.shadow_git_config_worktree = None
        self.git = None

    @property
    def base_hash(self) -> str:
        return self._base_hash

    @property
    def is_initialized(self) -> bool:
        return bool(self.git)
