"""Structured JSON logging helpers with file rotation."""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

_BASE_ATTRS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


def parse_log_level(level: str | int) -> int:
    if isinstance(level, int):
        return level

    normalized = level.strip().upper()
    mapping = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARN": logging.WARNING,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }
    return mapping.get(normalized, logging.INFO)


class JsonFormatter(logging.Formatter):
    """JSON formatter that preserves logging extras for structured events."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        for key, value in record.__dict__.items():
            if key in _BASE_ATTRS or key.startswith("_"):
                continue
            payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=True, default=str)


def configure_json_logger(
    name: str = "tcp_sim",
    level: str | int = logging.INFO,
    log_file: str | Path = "tcp-sim.log",
    max_bytes: int = 10485760,
    backup_count: int = 5,
    console: bool = False,
) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(parse_log_level(level))
    logger.propagate = False

    for handler in logger.handlers.copy():
        logger.removeHandler(handler)
        handler.close()

    formatter = JsonFormatter(datefmt="%Y-%m-%dT%H:%M:%S%z")

    output_path = Path(log_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rotating_handler = RotatingFileHandler(
        output_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    rotating_handler.setFormatter(formatter)
    logger.addHandler(rotating_handler)

    if console:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    return logger


def log_event(logger: logging.Logger, level: str | int, event: str, **fields: Any) -> None:
    log_level = parse_log_level(level)
    logger.log(log_level, event, extra={"event": event, **fields})
