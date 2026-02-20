"""Central logging configuration using loguru."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from loguru import logger as _BASE_LOGGER


_logger = _BASE_LOGGER


_REPO_ROOT = Path(__file__).resolve().parents[2]
_TRUE_VALUES = {"1", "true", "yes", "on"}


def _env_flag(name: str, default: bool) -> bool:
    """Return boolean environment flag with common truthy values."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in _TRUE_VALUES


def _compact_source(path_value: str) -> str:
    """Render source paths in compact repo-relative form for logs."""
    if not path_value:
        return "unknown"
    try:
        path = Path(path_value).expanduser().resolve()
    except OSError:
        return path_value

    as_text = str(path)
    site_packages = "site-packages/"
    if site_packages in as_text:
        return as_text.split(site_packages, 1)[1]
    try:
        return str(path.relative_to(_REPO_ROOT))
    except ValueError:
        return path.name


def _patch_record(record: dict) -> None:
    """Populate normalized source metadata for each log record."""
    extra = record["extra"]
    std_path = extra.get("std_path")
    std_line = extra.get("std_line")
    std_logger = extra.get("std_logger")

    source_path = str(std_path) if std_path else record["file"].path
    try:
        source_line = int(std_line) if std_line is not None else int(record["line"])
    except (TypeError, ValueError):
        source_line = int(record["line"])
    logger_name = str(std_logger) if std_logger else str(record["name"])

    extra["source"] = _compact_source(source_path)
    extra["source_line"] = source_line
    extra["logger_name"] = logger_name


def _format_record(_: dict) -> str:
    """Return the canonical loguru format string."""
    return (
        "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        "<level>{level:<8}</level> | "
        "<cyan>{extra[source]}:{extra[source_line]}</cyan> | "
        "<magenta>{extra[logger_name]}</magenta> | "
        "<level>{message}</level>\n"
    )


def _log_filter(record: dict) -> bool:
    """Hide noisy optional SDK logs unless explicitly enabled."""
    message = str(record.get("message") or "")
    if "Using bundled Claude Code CLI:" in message:
        return _env_flag("ACRETA_LOG_CLAUDE_SDK", default=False)
    return True


class _InterceptHandler(logging.Handler):
    """Forward stdlib logging records to loguru."""

    def emit(self, record: logging.LogRecord) -> None:
        """Forward one stdlib log record into loguru."""
        try:
            level = _logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        _logger.bind(
            std_logger=record.name,
            std_path=record.pathname,
            std_line=record.lineno,
            std_func=record.funcName,
        ).opt(exception=record.exc_info).log(level, record.getMessage())


def configure_logging(level: str | None = None) -> None:
    """Configure loguru and capture stdlib logging."""
    global _logger
    level = level or os.getenv("ACRETA_LOG_LEVEL", "INFO")
    colorize = _env_flag("ACRETA_LOG_COLOR", default=sys.stderr.isatty())

    _BASE_LOGGER.remove()
    _logger = _BASE_LOGGER.patch(_patch_record)
    _logger.add(
        sys.stderr,
        level=level,
        format=_format_record,
        filter=_log_filter,
        colorize=colorize,
        backtrace=False,
        diagnose=False,
    )

    logging.basicConfig(handlers=[_InterceptHandler()], level=0)

    # Ensure existing loggers propagate to root
    for name in list(logging.root.manager.loggerDict.keys()):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True


configure_logging()

logger = _logger

__all__ = ["logger", "configure_logging"]


if __name__ == "__main__":
    configure_logging(level="INFO")
    logger.info("config.logging self-test passed")
