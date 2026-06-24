from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).with_name("extraction_schema.json")


@lru_cache(maxsize=1)
def load_extraction_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def allowed_node_labels() -> set[str]:
    schema = load_extraction_schema()
    return {str(item["label"]) for item in schema.get("nodes", [])}


def allowed_relationship_types() -> set[str]:
    schema = load_extraction_schema()
    return {str(item["type"]) for item in schema.get("relationships", [])}


def allowed_relationship_triples() -> set[tuple[str, str, str]]:
    schema = load_extraction_schema()
    return {
        (str(item["start"]), str(item["type"]), str(item["end"]))
        for item in schema.get("relationships", [])
    }


def validate_graph_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate extracted graph payload against the restricted schema.

    Expected payload shape:
    {
      "nodes": [{"label": "Term", "properties": {...}}],
      "relationships": [{"start_label": "Term", "type": "SUGGESTS_INTENT", "end_label": "Intent", ...}]
    }
    """
    labels = allowed_node_labels()
    rel_types = allowed_relationship_types()
    triples = allowed_relationship_triples()
    errors: list[str] = []

    for idx, node in enumerate(payload.get("nodes") or []):
        label = str((node or {}).get("label") or "")
        if label not in labels:
            errors.append(f"nodes[{idx}].label_not_allowed:{label}")

    for idx, rel in enumerate(payload.get("relationships") or []):
        start_label = str((rel or {}).get("start_label") or "")
        rel_type = str((rel or {}).get("type") or "")
        end_label = str((rel or {}).get("end_label") or "")

        if rel_type not in rel_types:
            errors.append(f"relationships[{idx}].type_not_allowed:{rel_type}")
            continue

        if (start_label, rel_type, end_label) not in triples:
            errors.append(
                f"relationships[{idx}].triple_not_allowed:{start_label}-{rel_type}->{end_label}"
            )

    return {
        "valid": not errors,
        "errors": errors,
        "allowed_node_labels": sorted(labels),
        "allowed_relationship_types": sorted(rel_types),
    }
