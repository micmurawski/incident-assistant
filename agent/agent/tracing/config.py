"""
Configuration module for PocketFlow tracing with Phoenix (via OpenTelemetry).
"""

import os
from dataclasses import dataclass
from typing import Optional

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        pass


@dataclass
class TracingConfig:
    """Configuration class for PocketFlow tracing with Arize Phoenix."""

    phoenix_endpoint: Optional[str] = None
    project_name: Optional[str] = None

    debug: bool = False
    trace_inputs: bool = True
    trace_outputs: bool = True
    trace_errors: bool = True

    session_id: Optional[str] = None
    user_id: Optional[str] = None

    @classmethod
    def from_env(cls, env_file: Optional[str] = None) -> "TracingConfig":
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()

        return cls(
            phoenix_endpoint=os.getenv(
                "PHOENIX_COLLECTOR_ENDPOINT", "http://localhost:6006"
            ),
            project_name=os.getenv("PHOENIX_PROJECT_NAME", "pocketflow"),
            debug=os.getenv("POCKETFLOW_TRACING_DEBUG", "false").lower() == "true",
            trace_inputs=os.getenv("POCKETFLOW_TRACE_INPUTS", "true").lower()
            == "true",
            trace_outputs=os.getenv("POCKETFLOW_TRACE_OUTPUTS", "true").lower()
            == "true",
            trace_errors=os.getenv("POCKETFLOW_TRACE_ERRORS", "true").lower()
            == "true",
            session_id=os.getenv("POCKETFLOW_SESSION_ID"),
            user_id=os.getenv("POCKETFLOW_USER_ID"),
        )

    def validate(self) -> bool:
        if not self.phoenix_endpoint:
            if self.debug:
                print("Warning: PHOENIX_COLLECTOR_ENDPOINT not set")
            return False

        return True
