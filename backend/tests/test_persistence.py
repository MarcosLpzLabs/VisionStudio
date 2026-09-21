"""Pruebas de la capa de persistencia de proyectos (fase 9).

Cubren el round-trip del formato v1, el rechazo de versiones no soportadas y
el encadenamiento de migraciones (registro ficticio v0 -> v1), incluidos los
fallos de migración (ausente o errónea). No requieren hardware: son datos puros.
"""

import pytest

from visionstudio.errors import EngineError, ErrorCode
from visionstudio.persistence.migrations import MIGRATIONS, MigrationRegistry
from visionstudio.persistence.project import (
    CURRENT_FORMAT_VERSION,
    project_from_dict,
    project_to_dict,
)


# --- Fixtures de proyectos -------------------------------------------------

def proyecto_numerico() -> dict:
    """Proyecto v1 con un flujo numérico simple (compare -> sink_boolean)."""
    return {
        "format_version": 1,
        "name": "demo",
        "language": "en",
        "camera": {"index": 1, "width": 320, "height": 240},
        "flow": {"mode": "timer", "interval_ms": 250},
        "blocks": [
            {"id": "n1", "type": "block.numeric_value", "x": 10, "y": 20, "params": {"value": 5}},
            {"id": "c1", "type": "block.compare", "x": 30, "y": 40, "params": {"op": ">=", "reference": 3}},
            {"id": "s1", "type": "block.sink_boolean", "x": 50, "y": 60, "params": {}},
        ],
        "connections": [
            {"from": {"block": "n1", "port": "out"}, "to": {"block": "c1", "port": "in"}},
            {"from": {"block": "c1", "port": "out"}, "to": {"block": "s1", "port": "in"}},
        ],
    }


# --- Round-trip ------------------------------------------------------------

def test_round_trip_preserva_grafo_y_metadatos():
    graph, meta = project_from_dict(proyecto_numerico(), None)
    restored = project_to_dict(graph, meta)

    assert restored["format_version"] == CURRENT_FORMAT_VERSION
    assert restored["name"] == "demo"
    assert restored["language"] == "en"
    assert restored["camera"] == {"index": 1, "width": 320, "height": 240}
    assert restored["flow"] == {"mode": "timer", "interval_ms": 250}
    # Mismo número de bloques/conexiones; el grafo es estructuralmente igual.
    assert len(restored["blocks"]) == 3
    assert len(restored["connections"]) == 2
    # El round-trip del grafo con el que venimos: ids y tipos estables.
    assert {b["id"] for b in restored["blocks"]} == {"n1", "c1", "s1"}


def test_project_from_dict_tolerante_con_campos_ausentes():
    data = {"format_version": 1}
    graph, meta = project_from_dict(data, None)
    assert meta.name == "Untitled"
    assert meta.language == "es"
    assert graph.nodes == [] and graph.edges == []


def test_migracion_v1_a_v2_anade_tamano_automatico():
    # Un proyecto v1 (sin width/height) se migra a v2 con tamaño automático.
    graph, meta = project_from_dict(proyecto_numerico(), None)
    assert graph.node("n1").width is None
    assert graph.node("n1").height is None
    restored = project_to_dict(graph, meta)
    assert restored["format_version"] == CURRENT_FORMAT_VERSION
    assert all("width" in b and "height" in b for b in restored["blocks"])


def test_round_trip_con_tamano_explicito():
    # Un proyecto v2 con tamaño fijo lo conserva al guardar y cargar.
    data = proyecto_numerico()
    data["format_version"] = 2
    data["blocks"][0]["width"] = 220
    data["blocks"][0]["height"] = 90
    graph, meta = project_from_dict(data, None)
    assert graph.node("n1").width == 220
    assert graph.node("n1").height == 90
    restored = project_to_dict(graph, meta)
    assert restored["blocks"][0]["width"] == 220
    assert restored["blocks"][0]["height"] == 90


# --- Rechazo de versiones --------------------------------------------------

def test_rechaza_version_futura():
    data = proyecto_numerico()
    data["format_version"] = CURRENT_FORMAT_VERSION + 1
    with pytest.raises(EngineError) as exc:
        project_from_dict(data, None)
    assert exc.value.code == ErrorCode.PROJECT_VERSION_UNSUPPORTED


def test_rechaza_version_ausente():
    data = proyecto_numerico()
    data.pop("format_version")
    with pytest.raises(EngineError) as exc:
        project_from_dict(data, None)
    assert exc.value.code == ErrorCode.PROJECT_VERSION_UNSUPPORTED


def test_rechaza_version_no_entera():
    data = proyecto_numerico()
    data["format_version"] = "1"
    with pytest.raises(EngineError) as exc:
        project_from_dict(data, None)
    assert exc.value.code == ErrorCode.PROJECT_VERSION_UNSUPPORTED


# --- Migraciones -----------------------------------------------------------

def test_cadena_de_migraciones_v0_a_v1():
    # Registro aislado para no contaminar el global MIGRATIONS.
    reg = MigrationRegistry()

    # v0 guarda el modo como "timer_ms" (número); v1 lo renombra a "mode".
    def migrar_v0_a_v1(data):
        data = dict(data)
        data["format_version"] = 1
        if "flow" in data and isinstance(data["flow"], dict) and "timer_ms" in data["flow"]:
            data["flow"]["mode"] = "timer" if data["flow"].pop("timer_ms") else "continuous"
        return data

    reg.register(0, 1, migrar_v0_a_v1)

    v0 = {
        "format_version": 0,
        "name": "viejo",
        "blocks": [
            {"id": "n1", "type": "block.numeric_value", "x": 0, "y": 0, "params": {}}
        ],
        "connections": [],
        "flow": {"timer_ms": 1, "interval_ms": 200},
    }
    migrated = reg.apply(v0, 0, 1)
    # La migración se aplicó y declaró la nueva versión.
    assert migrated["format_version"] == 1
    assert migrated["flow"]["mode"] == "timer"
    assert "timer_ms" not in migrated["flow"]

    # Y el proyecto migrado se carga con project_from_dict sin problema.
    graph, meta = project_from_dict(migrated, None)
    assert meta.mode == "timer"
    assert meta.interval_ms == 200
    assert len(graph.nodes) == 1


def test_project_from_dict_aplica_migraciones_a_version_antigua():
    # Reutilizamos el registro global con una migración v0->v1 registrada solo
    # durante esta prueba (se limpia al terminar).
    def migrar_v0_a_v1(data):
        data = dict(data)
        data["format_version"] = 1
        return data

    MIGRATIONS.register(0, 1, migrar_v0_a_v1)
    try:
        v0 = proyecto_numerico()
        v0["format_version"] = 0
        graph, meta = project_from_dict(v0, None)
        # El parseo se hizo sobre el dict ya migrado: bloques presentes.
        assert len(graph.nodes) == 3
        assert len(graph.edges) == 2
    finally:
        MIGRATIONS._migrations.pop(0, None)


def test_migracion_ausente_lanza_error():
    reg = MigrationRegistry()  # sin migraciones registradas
    with pytest.raises(EngineError) as exc:
        reg.apply({"format_version": 0}, 0, 1)
    assert exc.value.code == ErrorCode.MIGRATION_FAILED


def test_migracion_que_falla_lanza_error():
    reg = MigrationRegistry()

    def migrar_rota(data):
        raise RuntimeError("fallo interno")

    reg.register(0, 1, migrar_rota)
    with pytest.raises(EngineError) as exc:
        reg.apply({"format_version": 0}, 0, 1)
    assert exc.value.code == ErrorCode.MIGRATION_FAILED
    assert "fallo interno" in exc.value.params["detail"]


def test_migracion_que_no_actualiza_version_lanza_error():
    reg = MigrationRegistry()

    def migrar_olvidada(data):
        return dict(data)  # no toca format_version -> bug de la migración

    reg.register(0, 1, migrar_olvidada)
    with pytest.raises(EngineError) as exc:
        reg.apply({"format_version": 0}, 0, 1)
    assert exc.value.code == ErrorCode.MIGRATION_FAILED


def test_registro_rechaza_saltos_de_varias_versiones():
    reg = MigrationRegistry()
    with pytest.raises(ValueError):
        reg.register(0, 2, lambda d: d)  # v0 -> v2 no es un paso único


def test_registro_rechaza_duplicados():
    reg = MigrationRegistry()
    reg.register(0, 1, lambda d: d)
    with pytest.raises(ValueError):
        reg.register(0, 1, lambda d: d)


# --- Datos corruptos -------------------------------------------------------

def test_ids_de_bloque_duplicados_rechazados():
    data = proyecto_numerico()
    data["blocks"] = [
        {"id": "n1", "type": "block.numeric_value", "x": 0, "y": 0, "params": {}},
        {"id": "n1", "type": "block.coordinates", "x": 1, "y": 1, "params": {}},
    ]
    with pytest.raises(EngineError) as exc:
        project_from_dict(data, None)
    assert exc.value.code == ErrorCode.BLOCK_NOT_FOUND