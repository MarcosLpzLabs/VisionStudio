"""Pruebas de integridad del catálogo i18n (fase 10).

El backend no contiene textos: emite códigos y claves. El catálogo es/en vive en
`frontend/src/i18n`. Estas pruebas leen esos JSON y comprueban que:

- `es` y `en` tienen exactamente las mismas claves (paridad).
- Cada `ErrorCode` tiene su clave `err.<code>` y existe `err.generic`.
- Cada `detail` estable conocido tiene su clave `err.detail.<code>`.
- Cada bloque (`ALL_BLOCKS`) tiene nombre, descripción, y etiquetas de puertos y
  parámetros en ambos idiomas.
- Las claves de categorías, tipos y estados usadas por la interfaz existen.

Si alguien añade un bloque, un código de error o una clave nueva sin traducirla,
estas pruebas fallan y evitan regresiones de i18n.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from visionstudio.blocks.specs import ALL_BLOCKS
from visionstudio.errors import ErrorCode
from visionstudio.types import ValueType

# Directorio raíz del repositorio: este archivo está en backend/tests/.
REPO_ROOT = Path(__file__).resolve().parents[2]
I18N_DIR = REPO_ROOT / "frontend" / "src" / "i18n"

# Idiomas soportados por contrato.
LANGUAGES = ("es", "en")

# Claves de `detail` estables que el backend puede enviar en `params.detail`.
# Deben coincidir con docs/CONTRATOS.md §4 y con las normalizaciones del código.
KNOWN_DETAILS = (
    "no_frame",
    "no_executor",
    "source_did_not_produce",
    "kernel_odd",
    "operator_unsupported",
    "mode_unknown",
    "duplicate_id",
    "invalid_project",
    "catalog",
)


def load_catalog(language: str) -> dict[str, str]:
    """Carga el catálogo JSON de un idioma."""
    with (I18N_DIR / f"{language}.json").open(encoding="utf-8") as handle:
        return json.load(handle)


def test_catalogos_cargan_y_son_dicts_de_strings() -> None:
    # Cada catálogo debe ser un objeto plano clave -> texto.
    for language in LANGUAGES:
        catalog = load_catalog(language)
        assert isinstance(catalog, dict)
        assert all(isinstance(k, str) and isinstance(v, str) for k, v in catalog.items())


def test_paridad_es_en() -> None:
    # Ambos idiomas deben exponer EXACTAMENTE el mismo conjunto de claves.
    es = set(load_catalog("es"))
    en = set(load_catalog("en"))
    assert es == en, f"claves solo en es: {sorted(es - en)}; solo en en: {sorted(en - es)}"


@pytest.mark.parametrize("language", LANGUAGES)
def test_todos_los_error_codes_traducidos(language: str) -> None:
    # Todo atributo ERR_* de ErrorCode debe tener clave err.<code>.
    catalog = load_catalog(language)
    codes = [value for name, value in vars(ErrorCode).items() if name.isupper()]
    assert codes, "ErrorCode no expone códigos"
    missing = [code for code in codes if f"err.{code}" not in catalog]
    assert not missing, f"sin traducción en {language}: {missing}"
    # El mensaje genérico de respaldo también debe existir.
    assert "err.generic" in catalog


@pytest.mark.parametrize("language", LANGUAGES)
def test_details_conocidos_traducidos(language: str) -> None:
    # Cada `detail` estable conocido debe resolverse con err.detail.<clave>.
    catalog = load_catalog(language)
    missing = [d for d in KNOWN_DETAILS if f"err.detail.{d}" not in catalog]
    assert not missing, f"sin err.detail.* en {language}: {missing}"


@pytest.mark.parametrize("language", LANGUAGES)
def test_claves_de_bloques_traducidas(language: str) -> None:
    # Todo nombre, descripción, puerto y parámetro de los bloques debe existir.
    catalog = load_catalog(language)
    missing: list[str] = []
    for spec in ALL_BLOCKS:
        for key in (spec.name_key, spec.description_key):
            if key not in catalog:
                missing.append(key)
        for port in (*spec.inputs, *spec.outputs):
            if port.label_key not in catalog:
                missing.append(port.label_key)
        for param in spec.params:
            if param.label_key not in catalog:
                missing.append(param.label_key)
    assert not missing, f"claves de bloques sin traducir en {language}: {sorted(set(missing))}"


@pytest.mark.parametrize("language", LANGUAGES)
def test_claves_auxiliares_de_interfaz(language: str) -> None:
    # Categorías, tipos de datos, estados, idiomas y etiquetas de UI presentes.
    catalog = load_catalog(language)
    auxiliary = [
        "library.title",
        "properties.title",
        "errors.title",
        "status.connected",
        "language.es",
        "language.en",
        "state.stopped",
        "state.running",
        "state.paused",
    ]
    auxiliary += [f"category.{category}" for category in ("source", "control", "processing", "analysis", "output")]
    auxiliary += [f"type.{value_type}" for value_type in ValueType.ALL]
    # El frontend usa "type.any" para puertos con demasiados tipos.
    auxiliary.append("type.any")
    missing = [key for key in auxiliary if key not in catalog]
    assert not missing, f"claves auxiliares sin traducir en {language}: {missing}"
