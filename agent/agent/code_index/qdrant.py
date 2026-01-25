import asyncio
import os
import sys

import docker

DEFAULT_CONTAINER_NAME = "agentleman-qdrant"


def run_qdrant_container(
    cwd: str | None = None, volume_path: str | None = None, container_name: str | None = DEFAULT_CONTAINER_NAME
):
    if os.environ.get("DOCKER_HOST") is None and sys.platform == "darwin":
        user = os.environ["USER"]
        client = docker.DockerClient(base_url=f"unix:///Users/{user}/.docker/run/docker.sock")
    else:
        client = docker.from_env()

    if cwd is None:
        cwd = os.getcwd()
    if volume_path is None:
        volume_path = os.path.join(cwd, "qdrant_storage")
    os.makedirs(volume_path, exist_ok=True)

    not_found = False

    try:
        container = client.containers.get(container_name)
        if container.attrs["State"]["Running"]:
            print(f"Using existing running container: {container.id}")
            return container
        else:
            container.start()
            return container
    except docker.errors.NotFound:
        print(f"Container {container_name} not found. Starting new container...")
        not_found = True

    if not_found:
        try:
            volume = client.volumes.create(name='qdrant_storage')
            container = client.containers.run(
                "qdrant/qdrant",
                ports={
                    "6333/tcp": 6333,
                    "6334/tcp": 6334,
                },
                volumes={volume.id: {"bind": "/qdrant/storage", "mode": "z"}},
                detach=True,  # Run in background
                name=container_name,  # Optional: give the container a name
            )

            print("Container started successfully!")
            print(f"Container ID: {container.id}")
            print(f"Container name: {container.name}")
            print(f"Volume mounted: {volume_path} -> /qdrant/storage")
            print("Ports: 6333 and 6334 are exposed")
        except docker.errors.ImageNotFound:
            print("Qdrant image not found. Pulling from Docker Hub...")
            client.images.pull("qdrant/qdrant")
            # Retry running the container
            volume = client.volumes.create(name='qdrant_storage')
            container = client.containers.run(
                "qdrant/qdrant",
                ports={
                    "6333/tcp": 6333,
                    "6334/tcp": 6334,
                },
                volumes={volume.id: {"bind": "/qdrant/storage", "mode": "z"}},
                detach=True,
                name=container_name,
            )
            print("Container started successfully after pulling image!")


def stop_qdrant_container(container_name: str | None = DEFAULT_CONTAINER_NAME):
    if os.environ.get("DOCKER_HOST") is None and sys.platform == "darwin":
        user = os.environ["USER"]
        client = docker.DockerClient(base_url=f"unix:///Users/{user}/.docker/run/docker.sock")
    else:
        client = docker.from_env()
    client.containers.get(container_name).stop()


async def main():
    run_qdrant_container()
    # stop_qdrant_container()


if __name__ == "__main__":
    asyncio.run(main())
