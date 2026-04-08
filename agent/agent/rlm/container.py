import asyncio
import io
import socket
import time
from pathlib import Path
from typing import Dict, List

import docker
import httpx
import pandas as pd

_SANDBOX_SERVER = Path(__file__).resolve().parent / "sandbox_server.py"


class ContainerRLMSandbox:
    def __init__(
        self,
        container_name: str = "llm-sandbox",
        port: int | None = None,
        image: str = "python:3.12-slim",
        env: Dict[str, str] | None = None,
    ):
        self.client: docker.DockerClient | None = None
        self.container_name = container_name
        self.port = port
        self.image = image
        self.env = env or {}
        self._http_base: str = ""
        self.history: List[Dict[str, str]] = []
        self.container = None

    def _docker(self) -> docker.DockerClient:
        if self.client is None:
            self.client = docker.from_env()
        return self.client

    def _resolve_host_port(self) -> int:
        assert self.container is not None
        self.container.reload()
        ports = self.container.attrs.get("NetworkSettings", {}).get("Ports") or {}
        mapping = ports.get("8000/tcp")
        if not mapping:
            logs = self.container.logs(tail=80).decode(errors="replace")
            raise RuntimeError(f"No host port mapped for 8000/tcp. Container logs:\n{logs}")
        return int(mapping[0]["HostPort"])

    def _wait_for_port(self, timeout: float = 180.0) -> None:
        assert self.port is not None
        deadline = time.time() + timeout
        last_err: OSError | None = None
        while time.time() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", self.port), timeout=2):
                    return
            except OSError as e:
                last_err = e
            if self.container:
                self.container.reload()
                if self.container.status != "running":
                    logs = self.container.logs(tail=120).decode(errors="replace")
                    raise RuntimeError(f"Sandbox container stopped ({self.container.status}). Logs:\n{logs}")
            time.sleep(0.5)
        raise TimeoutError(f"Port {self.port} did not open within {timeout}s: {last_err}")

    def _wait_for_health(self, timeout: float = 180.0) -> None:
        assert self.port is not None
        url = f"http://127.0.0.1:{self.port}/health"
        deadline = time.time() + timeout
        last_err: Exception | None = None
        while time.time() < deadline:
            try:
                with httpx.Client(timeout=5.0) as client:
                    r = client.get(url)
                    if r.status_code == 200 and r.text.strip() == "ok":
                        return
            except Exception as e:
                last_err = e
            if self.container:
                self.container.reload()
                if self.container.status != "running":
                    logs = self.container.logs(tail=120).decode(errors="replace")
                    raise RuntimeError(f"Sandbox container stopped ({self.container.status}). Logs:\n{logs}")
            time.sleep(0.5)
        raise TimeoutError(f"Sandbox /health did not become ready within {timeout}s: {last_err}")

    def start(self, volumes: Dict[str, Dict[str, str]] | None = None) -> None:
        print(f"Booting secure sandbox ({self.image})...")

        try:
            old_container = self._docker().containers.get(self.container_name)
            old_container.remove(force=True)
        except docker.errors.NotFound:
            pass

        if not _SANDBOX_SERVER.is_file():
            raise FileNotFoundError(f"Missing sandbox server file: {_SANDBOX_SERVER}")

        port_kw: dict = {}
        if self.port is not None:
            port_kw["ports"] = {"8000/tcp": self.port}
        else:
            port_kw["ports"] = {"8000/tcp": None}

        boot = (
            "pip install --no-cache-dir -q starlette 'uvicorn[standard]' && "
            "python -m uvicorn sandbox_server:app --host 0.0.0.0 --port 8000"
        )

        container_volumes = {str(_SANDBOX_SERVER): {"bind": "/app/sandbox_server.py", "mode": "ro"}}
        if volumes:
            container_volumes.update(volumes)

        self.container = self._docker().containers.run(
            self.image,
            name=self.container_name,
            detach=True,
            volumes=container_volumes,
            environment=self.env,
            working_dir="/app",
            command=["sh", "-c", boot],
            mem_limit="1g",
            nano_cpus=1000000000,
            network_mode="bridge",
            auto_remove=True,
            **port_kw,
        )

        if self.port is None:
            self.port = self._resolve_host_port()
        self._http_base = f"http://127.0.0.1:{self.port}"

        self._wait_for_port()
        self._wait_for_health()

        short = getattr(self.container, "short_id", None) or (self.container.id or "")[:12]
        self.history.append({"action": "SYSTEM", "content": f"Sandbox started (ID: {short})"})

        if self.port is None:
            self.port = self._resolve_host_port()
        self._http_base = f"http://127.0.0.1:{self.port}"

        self._wait_for_port()
        self._wait_for_health()

        short = getattr(self.container, "short_id", None) or (self.container.id or "")[:12]
        self.history.append({"action": "SYSTEM", "content": f"Sandbox started (ID: {short})"})

    def reset_interpreter(self) -> None:
        if self.container:
            try:
                self.container.stop()
            except Exception:
                pass
        self.start()
        self.history.append({"action": "SYSTEM", "content": "Interpreter state wiped. Fresh container initialized."})

    async def load_python_file(self, file_path: str | Path) -> None:
        if not isinstance(file_path, Path):
            file_path = Path(file_path)
        if not file_path.is_file():
            raise FileNotFoundError(f"File not found: {file_path}")
        with open(file_path, "r") as f:
            code = f.read()
        return await self.execute_code(code)

    async def upload_file(self, content: str, filename: str) -> None:
        """Upload a file to the sandbox."""
        import base64
        b64_content = base64.b64encode(content.encode("utf-8")).decode("utf-8")
        code = f"""
import base64
with open({repr(filename)}, "wb") as f:
    f.write(base64.b64decode({repr(b64_content)}))
"""
        await self.execute_code(code)

    async def upload_dataframe(self, df: 'pd.DataFrame', name: str) -> None:
        """Upload a pandas DataFrame to the sandbox as a CSV variable."""
        csv_data = df.to_csv(index=False)
        code = f"""
import pandas as pd
import io
{name} = pd.read_csv(io.StringIO({repr(csv_data)}))
print(f"Loaded DataFrame '{name}' with {{len({name})}} rows.")
"""
        out, err = await self.execute_code(code)
        if err:
            return f"Error loading dataframe: {err}"
        return out

    async def download_file(self, filename: str) -> str:
        """Download a file from the sandbox."""
        code = f"""
with open({repr(filename)}, "r") as f:
    print(f.read())
"""
        out, err = await self.execute_code(code)
        if err:
            return f"Error downloading file: {err}"
        return out

    async def pip_install(self, packages: list[str]) -> None:
        code = f"""
import subprocess, sys
packages = {repr(packages)}
print(f"Installing {{', '.join(packages)}}...")
subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *packages])
"""
        out, err = await self.execute_code(code)
        if err:
            raise Exception(f"Pip install failed: {err}")

    async def execute_code(self, code: str) -> tuple[str, str | None]:
        url = f"{self._http_base}/run"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(300.0)) as client:
                r = await client.post(url, content=code.encode("utf-8"))
                r.raise_for_status()
                data = r.json()
                output = data.get("output", "")
                error = data.get("error")

            self.history.append({"action": "CODE_INPUT", "content": code})
            if error:
                self.history.append({"action": "CODE_ERROR", "content": error})
            self.history.append({"action": "CODE_OUTPUT", "content": output})

            return output, error

        except Exception as e:
            error_msg = f"Network/Execution Error: {str(e)}"
            self.history.append({"action": "ERROR", "content": error_msg})
            if self.container:
                try:
                    logs = self.container.logs(tail=40).decode(errors="replace")
                    error_msg = f"{error_msg}\n--- container logs (tail) ---\n{logs}"
                except Exception:
                    pass
            return "", error_msg

    def reset_history(self) -> None:
        self.history = []

    def get_history(self) -> List[Dict[str, str]]:
        return self.history

    def shutdown(self) -> None:
        if self.container:
            try:
                self.container.stop()
            except Exception:
                pass


class DataScienceSandbox(ContainerRLMSandbox):
    """
    Specialized sandbox for data science tasks.
    Pre-installs common libraries and supports state sharing.
    """

    def __init__(self, container_name: str = "ds-sandbox", **kwargs):
        super().__init__(container_name=container_name, **kwargs)

    async def prepare(self, packages: list[str] | None = None) -> None:
        """Install data science stack."""
        if packages is None:
            packages = ["pandas", "numpy", "matplotlib", "seaborn", "scipy"]
        await self.pip_install(packages)

    async def export_dataframe(self, name: str) -> 'pd.DataFrame':
        """Download a DataFrame from the sandbox."""
        code = f"print({name}.to_csv(index=False))"
        csv_output = await self.execute_code(code)
        # Handle potential stdout noise before CSV
        if "Loaded DataFrame" in csv_output:
            csv_output = csv_output.split("\n", 1)[1]
        return pd.read_csv(io.StringIO(csv_output))


def dict_to_str(d: Dict[str, str | int | float | bool | dict]) -> str:
    vals = []
    for k, v in d.items():
        if isinstance(v, dict):
            vals.append(f"{k}={dict_to_str(v)}")
        else:
            vals.append(f"{k}={v}")
    return "\n".join(vals)


class ContainersResourceManager:
    containers: Dict[str, ContainerRLMSandbox] = {}

    @classmethod
    def does_container_exist(cls, id: str, ds: bool = False, **kwargs) -> bool:
        _id = dict_to_str({**kwargs, "id": id, "ds": ds})
        return _id in cls.containers

    @classmethod
    def get_container(cls, id: str, ds: bool = False, **kwargs) -> ContainerRLMSandbox:
        _id = dict_to_str({**kwargs, "id": id, "ds": ds})
        if _id not in cls.containers:
            if ds:
                cls.containers[_id] = DataScienceSandbox(container_name=id, **kwargs)
            else:
                cls.containers[_id] = ContainerRLMSandbox(container_name=id, **kwargs)
            cls.containers[_id].start()
        return cls.containers[_id]

    @classmethod
    def reset_container(cls, id: str) -> None:
        if id in cls.containers:
            cls.containers[id].reset_interpreter()

    @classmethod
    def shutdown_container(cls, id: str) -> None:
        if id in cls.containers:
            cls.containers[id].shutdown()
            del cls.containers[id]


async def main() -> None:
    container = ContainersResourceManager.get_container("test")
    result = await container.execute_code("print('Hello, World!')")
    print(result)
    result = await container.execute_code("x=1")
    print(result)
    result = await container.execute_code("print(x)")
    print(result)
    ContainersResourceManager.shutdown_container("test")


if __name__ == "__main__":
    asyncio.run(main())
