from dataclasses import dataclass



@dataclass
class Datasource:
    """Grafana datasource info."""

    uid: str
    type: str
    name: str


class GrafanaBadRequestError(Exception):
    """Exception raised for Grafana bad request errors."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(self.message)


class BaseGrafanaClient:
    """Base logic for Grafana API clients."""

    def __init__(self, url: str, api_key: str):
        self.url = url.rstrip("/")
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
