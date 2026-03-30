import asyncio
import socket
import time
from pathlib import Path
from typing import Dict, List

import docker
import httpx

_SANDBOX_SERVER = Path(__file__).resolve().parent / "sandbox_server.py"


class ContainerRLMSandbox:
    def __init__(self, container_name: str = "llm-sandbox", port: int | None = None):
        self.client: docker.DockerClient | None = None
        self.container_name = container_name
        self.port = port
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

    def start(self) -> None:
        print("Booting secure sandbox...")

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

        self.container = self._docker().containers.run(
            "python:3.13-alpine",
            name=self.container_name,
            detach=True,
            volumes={str(_SANDBOX_SERVER): {"bind": "/app/sandbox_server.py", "mode": "ro"}},
            working_dir="/app",
            command=["sh", "-c", boot],
            mem_limit="512m",
            nano_cpus=500000000,
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
        if not file_path.suffix == ".py":
            raise ValueError(f"File is not a Python file: {file_path}")
        with open(file_path, "r") as f:
            code = f.read()
        return await self.execute_code(code)

    async def pip_install(self, packages: list[str]) -> None:
        code = f"""
        import subprocess, sys
        packages = [{', '.join(packages)}]
        subprocess.check_call([sys.executable, "-m", "pip", "install", *packages])
        """
        return await self.execute_code(code)

    async def execute_code(self, code: str) -> str:
        url = f"{self._http_base}/run"
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
                r = await client.post(url, content=code.encode("utf-8"))
                r.raise_for_status()
                output = r.text

            self.history.append({"action": "CODE_INPUT", "content": code})
            self.history.append({"action": "CODE_OUTPUT", "content": output})

            return output

        except Exception as e:
            error_msg = f"Network/Execution Error: {str(e)}"
            self.history.append({"action": "ERROR", "content": error_msg})
            if self.container:
                try:
                    logs = self.container.logs(tail=40).decode(errors="replace")
                    return f"{error_msg}\n--- container logs (tail) ---\n{logs}"
                except Exception:
                    pass
            return error_msg

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


class ContainersResourceManager:
    containers: Dict[str, ContainerRLMSandbox] = {}

    @classmethod
    def get_container(cls, id: str) -> ContainerRLMSandbox:
        if id not in cls.containers:
            cls.containers[id] = ContainerRLMSandbox(container_name=f"llm-sandbox-{id}")
            cls.containers[id].start()
        return cls.containers[id]

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
