from abc import ABC, abstractmethod


class BaseDetector(ABC):
    @abstractmethod
    def process(self, trade: dict) -> dict | None:
        """
        Receive one validated trade. Return a signal dict if a signal fired,
        or None otherwise.
        """

    @abstractmethod
    def reset(self) -> None:
        """Reset all rolling windows and internal state (called on reconnect)."""
