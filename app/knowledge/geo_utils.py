"""
Utilidades geográficas para la ZM Laguna / Comarca Lagunera.

Carga el catálogo data/zm_laguna_localities.json una sola vez al importar
y expone funciones de normalización e identificación de localidades locales.
"""
import json
import os
import unicodedata

_CATALOG_PATH = os.path.join(
    os.path.dirname(__file__), "zm_laguna_localities.json"
)

def _normalize(text: str) -> str:
    """Lowercase + strip diacríticos para comparación."""
    nfkd = unicodedata.normalize("NFKD", text.lower().strip())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _build_index(catalog_path: str) -> tuple[dict[str, str], set[str]]:
    """
    Construye:
    - alias_to_canonical: {alias_normalizado → nombre_canónico}
    - canonical_set: {canonical_normalizado} para is_zm_laguna_canonical
    """
    alias_map: dict[str, str] = {}
    canonical_set: set[str] = set()

    try:
        with open(catalog_path, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return alias_map, canonical_set

    for section in ("zm_laguna", "comarca_ampliada"):
        for municipality in data.get(section, []):
            canonical = municipality["canonical"]
            canonical_set.add(_normalize(canonical))
            # aliases del municipio
            for alias in municipality.get("aliases", []):
                alias_map[_normalize(alias)] = canonical
            # alias = el canónico mismo
            alias_map[_normalize(canonical)] = canonical
            # localidades del municipio
            for loc in municipality.get("localities", []):
                loc_canonical = loc["canonical"]
                for alias in loc.get("aliases", []):
                    alias_map[_normalize(alias)] = canonical  # → municipio anfitrión

    return alias_map, canonical_set


_ALIAS_MAP, _CANONICAL_SET = _build_index(_CATALOG_PATH)


def normalize_zm_laguna_city(raw: str) -> str:
    """
    Si raw es un alias conocido de la ZML/Comarca, devuelve el nombre canónico
    del municipio. Si no hay match, devuelve raw sin cambios.
    """
    if not raw:
        return raw
    key = _normalize(raw)
    return _ALIAS_MAP.get(key, raw)


def is_zm_laguna_canonical(city: str) -> bool:
    """
    True si city (ya normalizado/canónico) pertenece al catálogo ZML o Comarca ampliada.
    Comparación case-insensitive sin diacríticos.
    """
    if not city:
        return False
    return _normalize(city) in _CANONICAL_SET
