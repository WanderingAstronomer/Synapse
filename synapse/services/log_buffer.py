"""
synapse.services.log_buffer — In-Memory Ring Buffer for Live Log Viewing
=========================================================================

Provides a thread-safe ring buffer that plugs into Python's ``logging``
framework.  The API exposes ``get_logs()`` for tail-style reads and
``set_level()`` for on-the-fly log-level adjustments from the admin UI.

Architecture:
    Each process (bot, API) maintains its own buffer via a module-level
    singleton.  No persistence — logs are lost on restart by design.
    This is "stream of consciousness" debugging, not auditing.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import UTC, datetime

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DEFAULT_CAPACITY = 2000
VALID_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")

# Module-level singleton — one per process
_buffer: LogBuffer | None = None
_lock = threading.Lock()


class LogEntry:
    """One captured log record."""
    __slots__ = ("timestamp", "level", "logger", "message")

    def __init__(self, timestamp: str, level: str, logger: str, message: str):
        self.timestamp = timestamp
        self.level = level
        self.logger = logger
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "logger": self.logger,
            "message": self.message,
        }


class LogBuffer:
    """Thread-safe ring buffer backed by :class:`collections.deque`."""

    def __init__(self, capacity: int = DEFAULT_CAPACITY) -> None:
        self._entries: deque[LogEntry] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def append(self, entry: LogEntry) -> None:
        with self._lock:
            self._entries.append(entry)

    def get_entries(
        self,
        tail: int = 200,
        level: str | None = None,
        logger_filter: str | None = None,
    ) -> list[dict[str, str]]:
        """Return the most recent *tail* entries, optionally filtered."""
        min_level = getattr(logging, level.upper(), 0) if level else 0

        with self._lock:
            snapshot = list(self._entries)

        # Apply filters
        results: list[dict[str, str]] = []
        for entry in snapshot:
            # Level filter
            if min_level and getattr(logging, entry.level, 0) < min_level:
                continue
            # Logger filter (prefix match)
            if logger_filter and not entry.logger.startswith(logger_filter):
                continue
            results.append(entry.to_dict())

        # Return only the tail
        if tail and len(results) > tail:
            results = results[-tail:]

        return results

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._entries)


class RingBufferHandler(logging.Handler):
    """Logging handler that appends records to a :class:`LogBuffer`."""

    def __init__(self, buffer: LogBuffer, level: int = logging.DEBUG) -> None:
        super().__init__(level)
        self._buffer = buffer

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = LogEntry(
                timestamp=datetime.fromtimestamp(
                    record.created, tz=UTC
                ).isoformat(),
                level=record.levelname,
                logger=record.name,
                message=self.format(record) if self.formatter else record.getMessage(),
            )
            self._buffer.append(entry)
        except Exception:
            self.handleError(record)


# ---------------------------------------------------------------------------
# Singleton access
# ---------------------------------------------------------------------------
def get_buffer() -> LogBuffer:
    """Return (or create) the process-global log buffer."""
    global _buffer
    if _buffer is None:
        with _lock:
            if _buffer is None:
                _buffer = LogBuffer()
    return _buffer


def install_handler(level: int = logging.DEBUG) -> RingBufferHandler:
    """Install the ring-buffer handler on the root and uvicorn loggers.

    The handler captures records at *level* and above into the buffer.
    We explicitly attach to `uvicorn.access` and `uvicorn.error` because
    Uvicorn often disables propagation for these loggers.
    """
    buf = get_buffer()
    handler = RingBufferHandler(buf, level=level)
    handler.setFormatter(logging.Formatter("%(message)s"))

    # 1. Attach to root logger
    root = logging.getLogger()
    root.addHandler(handler)

    # 2. Force propagation on Uvicorn loggers so they bubble up to root
    # where our RingBufferHandler is attached.
    # Note: This may cause double-logging in the terminal (once from Uvicorn's
    # handler, once from root's handler), but it guarantees we capture them.
    for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        log = logging.getLogger(logger_name)
        log.propagate = True
        log.setLevel(logging.INFO)

    return handler


def get_logs(
    tail: int = 200,
    level: str | None = None,
    logger_filter: str | None = None,
) -> list[dict[str, str]]:
    """Convenience wrapper — fetch entries from the global buffer."""
    return get_buffer().get_entries(tail=tail, level=level, logger_filter=logger_filter)


def get_current_level() -> str:
    """Return the effective minimum level being captured to the buffer."""
    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, RingBufferHandler):
            return logging.getLevelName(h.level)
    return logging.getLevelName(root.level)


def set_capture_level(level_name: str) -> str:
    """Change the minimum level of the ring-buffer handler on-the-fly.

    Returns the new effective level name.
    """
    level_name = level_name.upper()
    if level_name not in VALID_LEVELS:
        raise ValueError(f"Invalid level: {level_name}. Must be one of {VALID_LEVELS}")

    numeric = getattr(logging, level_name)
    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h, RingBufferHandler):
            h.setLevel(numeric)
            return level_name

    # Fallback: no handler found — install one at the requested level
    install_handler(level=numeric)
    return level_name
