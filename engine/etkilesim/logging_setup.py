"""Yapılandırılmış (JSON satırı) günlük; sırlar (Telegram jetonu) otomatik temizlenir."""

from __future__ import annotations

import json
import logging
import sys
import uuid
from logging.handlers import RotatingFileHandler

from . import secrets_store
from .config import log_path

REQUEST_ID = uuid.uuid4().hex[:12]


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": REQUEST_ID,
            "msg": secrets_store.redact(record.getMessage()),
        }
        job = getattr(record, "job_id", None)
        if job is not None:
            payload["job_id"] = job
        if record.exc_info:
            payload["exc"] = secrets_store.redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configure(to_stderr: bool = False) -> logging.Logger:
    logger = logging.getLogger("etkilesim")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    formatter = JsonFormatter()
    file_handler = RotatingFileHandler(log_path(), maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    if to_stderr:
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(formatter)
        logger.addHandler(stream)
    logger.propagate = False
    return logger
