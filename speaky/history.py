"""History storage for recognition results"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)

MAX_HISTORY_SIZE = 50  # Maximum number of history items to keep


@dataclass
class HistoryItem:
    """A single history entry"""
    text: str
    timestamp: str  # ISO format string
    engine: str = ""

    @classmethod
    def create(cls, text: str, engine: str = "") -> "HistoryItem":
        """Create a new history item with current timestamp"""
        return cls(
            text=text,
            timestamp=datetime.now().isoformat(),
            engine=engine
        )


class HistoryManager:
    """Manages recognition history"""

    _instance: Optional["HistoryManager"] = None

    def __init__(self):
        self._history: List[HistoryItem] = []
        self._history_file = Path.home() / ".speaky" / "history.json"
        self._load()

    @classmethod
    def instance(cls) -> "HistoryManager":
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _load(self):
        """Load history from file"""
        try:
            if self._history_file.exists():
                with open(self._history_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self._history = [
                        HistoryItem(**item) for item in data
                    ]
                logger.info(f"Loaded {len(self._history)} history items")
        except Exception as e:
            logger.error(f"Failed to load history: {e}")
            self._history = []

    def _save(self):
        """Save history to file"""
        try:
            self._history_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self._history_file, "w", encoding="utf-8") as f:
                json.dump([asdict(item) for item in self._history], f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save history: {e}")

    def add(self, text: str, engine: str = ""):
        """Add a new recognition result to history"""
        if not text or not text.strip():
            return

        # Remove duplicates (same text within last 5 entries)
        text = text.strip()
        for i, item in enumerate(self._history[:5]):
            if item.text == text:
                # Move to front
                self._history.pop(i)
                break

        # Add to front
        item = HistoryItem.create(text, engine)
        self._history.insert(0, item)

        # Trim to max size
        if len(self._history) > MAX_HISTORY_SIZE:
            self._history = self._history[:MAX_HISTORY_SIZE]

        self._save()
        logger.info(f"Added to history: {text[:30]}...")

    def get_all(self) -> List[HistoryItem]:
        """Get all history items"""
        return self._history.copy()

    def get_recent(self, count: int = 10) -> List[HistoryItem]:
        """Get recent history items"""
        return self._history[:count]

    def clear(self):
        """Clear all history"""
        self._history = []
        self._save()
        logger.info("History cleared")

    def remove(self, index: int):
        """Remove history item at index"""
        if 0 <= index < len(self._history):
            self._history.pop(index)
            self._save()


# Convenience functions
def add_to_history(text: str, engine: str = ""):
    """Add text to history"""
    HistoryManager.instance().add(text, engine)


def get_history(count: int = 10) -> List[HistoryItem]:
    """Get recent history items"""
    return HistoryManager.instance().get_recent(count)


def clear_history():
    """Clear all history"""
    HistoryManager.instance().clear()
