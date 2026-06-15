from abc import ABC, abstractmethod
from typing import Any, Self


class BaseSandbox(ABC):

    @abstractmethod
    def start(self) -> None:
        pass

    @abstractmethod
    def execute(self, command: str, timeout: int = 300) -> dict[str, Any]:
        pass

    @abstractmethod
    def stop(self) -> None:
        pass

    def __enter__(self) -> Self:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()
