from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.rlm.container import (ContainerRLMSandbox,
                                     ContainersResourceManager)

__all__ = ["ContainerRLMSandbox", "ContainersResourceManager"]


def __getattr__(name: str):
    if name in __all__:
        from agent.rlm import container as _container

        return getattr(_container, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
