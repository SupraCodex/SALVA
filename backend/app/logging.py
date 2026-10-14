"""Structured JSON logs (NFR-14). Never log secrets, tokens, e-mails or free-text notes."""

from __future__ import annotations

import json
import logging

FIELDS = ("request_id", "path", "status", "ms", "user_id", "reason", "provider")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        data.update({k: getattr(record, k) for k in FIELDS if hasattr(record, k)})
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, ensure_ascii=False, default=str)


def setup(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
