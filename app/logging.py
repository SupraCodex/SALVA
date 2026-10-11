"""Structured JSON logs. Never log API keys or free-text user input in full."""
import json
import logging

FIELDS = ("request_id", "path", "status", "ms")


class JsonFormatter(logging.Formatter):
    def format(self, r: logging.LogRecord) -> str:
        d = {"level": r.levelname, "logger": r.name, "msg": r.getMessage()}
        d.update({k: getattr(r, k) for k in FIELDS if hasattr(r, k)})
        if r.exc_info:
            d["exc"] = self.formatException(r.exc_info)
        return json.dumps(d, ensure_ascii=False)


def setup() -> None:
    h = logging.StreamHandler()
    h.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[h], force=True)
