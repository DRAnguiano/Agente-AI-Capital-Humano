from __future__ import annotations

import logging
import os
import re

os.environ.setdefault("ANONYMIZED_TELEMETRY", "False")
os.environ.setdefault("CHROMA_TELEMETRY_DISABLED", "1")
os.environ.setdefault("DO_NOT_TRACK", "1")
os.environ.setdefault("POSTHOG_DISABLED", "1")

_NOISY_TELEMETRY_PATTERNS = (
    re.compile(r"Failed to send telemetry event .*capture\(\) takes 1 positional argument but 3 were given", re.IGNORECASE),
)


class _TelemetryNoiseFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True
        return not any(pattern.search(message) for pattern in _NOISY_TELEMETRY_PATTERNS)


_filter = _TelemetryNoiseFilter()
logging.getLogger().addFilter(_filter)

for _logger_name in (
    "chromadb",
    "chromadb.telemetry",
    "chromadb.telemetry.product",
    "posthog",
):
    _logger = logging.getLogger(_logger_name)
    _logger.addFilter(_filter)
    _logger.setLevel(logging.CRITICAL)
    _logger.propagate = False
