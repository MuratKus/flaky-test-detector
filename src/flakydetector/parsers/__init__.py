"""Base parser interface."""

from abc import ABC, abstractmethod
from pathlib import Path

from flakydetector.models import RunSummary


class BaseParser(ABC):
    """All parsers implement this interface."""

    @abstractmethod
    def can_parse(self, path: Path) -> bool:
        """Return True if this parser can handle the given file."""
        ...

    @abstractmethod
    def parse(self, path: Path, run_id: str) -> RunSummary:
        """Parse the file and return a RunSummary."""
        ...
