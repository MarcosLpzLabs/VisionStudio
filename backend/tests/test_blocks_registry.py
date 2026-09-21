"""Pruebas del registro de bloques."""

import pytest

from visionstudio.blocks import registry
from visionstudio.types import ValueType


def test_registro_expone_todos_los_bloques():
    # 21 bloques definidos en docs/CONTRATOS.md §3
    assert len(registry.all()) == 21


def test_ids_estables_esperados():
    esperados = {
        "block.camera",
        "block.timer",
        "block.manual_trigger",
        "block.pause_resume",
        "block.grayscale",
        "block.black_white",
        "block.threshold",
        "block.blur",
        "block.edge_detection",
        "block.contours",
        "block.draw_text",
        "block.ok_nok",
        "block.compare",
        "block.numeric_value",
        "block.coordinates",
        "block.rectangles",
        "block.detection_list",
        "block.sink_image",
        "block.sink_text",
        "block.sink_boolean",
        "block.status_indicator",
    }
    obtenidos = {s.id for s in registry.all()}
    assert obtenidos == esperados


def test_ids_unicos():
    ids = [s.id for s in registry.all()]
    assert len(ids) == len(set(ids))


def test_categorias():
    cats = registry.categories()
    assert set(cats) == {"source", "control", "processing", "analysis", "output"}
    assert any(s.id == "block.camera" for s in cats["source"])
    assert any(s.id == "block.grayscale" for s in cats["processing"])
    assert any(s.id == "block.sink_image" for s in cats["output"])


def test_claves_i18n_presentes():
    for spec in registry.all():
        assert spec.name_key
        assert spec.description_key
        for port in (*spec.inputs, *spec.outputs):
            assert port.label_key
        for p in spec.params:
            assert p.label_key


def test_parametros_por_defecto_serializables():
    import json

    for spec in registry.all():
        params = registry.default_params(spec.id)
        json.dumps(params)  # no debe lanzar


def test_validate_params_ok():
    assert registry.validate_params("block.camera", {"camera_index": 0, "width": 640, "height": 480}) is None


def test_validate_params_parametro_desconocido():
    err = registry.validate_params("block.camera", {"no_existe": 1})
    assert err is not None and err.startswith("param_unknown")


def test_validate_params_fuera_de_rango():
    err = registry.validate_params("block.blur", {"kernel": 0})
    assert err is not None and "below_min" in err


def test_validate_params_select_invalido():
    err = registry.validate_params(
        "block.threshold", {"threshold": 127, "max_value": 255, "type": "NO_EXISTE"}
    )
    assert err is not None and "not_an_option" in err


def test_validate_params_color():
    params_ok = {"text": "hola", "x": 0, "y": 0, "size": 1.0}
    err = registry.validate_params("block.draw_text", {**params_ok, "color": [0, 300, 0]})
    assert err is not None and "not_a_color" in err
    assert registry.validate_params("block.draw_text", {**params_ok, "color": [0, 255, 0]}) is None


def test_validate_params_entero():
    err = registry.validate_params("block.camera", {"camera_index": 1.5})
    assert err is not None and "not_an_integer" in err


def test_validate_params_impar_obligatorio():
    # El núcleo de blur debe ser impar: 5 vale, 4 se rechaza con "not_odd".
    assert registry.validate_params("block.blur", {"kernel": 5}) is None
    err = registry.validate_params("block.blur", {"kernel": 4})
    assert err is not None and "not_odd" in err
    # El rango se comprueba antes que la paridad: 0 -> below_min (no not_odd).
    err0 = registry.validate_params("block.blur", {"kernel": 0})
    assert err0 is not None and "below_min" in err0


def test_compatibilidad_conexiones():
    assert registry.compatible(ValueType.FRAME, "block.grayscale", "in")
    assert not registry.compatible(ValueType.NUMBER, "block.grayscale", "in")
    # status_indicator acepta boolean o analysis
    assert registry.compatible(ValueType.ANALYSIS, "block.status_indicator", "in")
    assert registry.compatible(ValueType.BOOLEAN, "block.status_indicator", "in")


def test_get_desconocido_levanta_keyerror():
    with pytest.raises(KeyError):
        registry.get("block.no_existe")


def test_puerto_desconocido_levanta_keyerror():
    with pytest.raises(KeyError):
        registry.get("block.camera").port("no_existe")


def test_parametro_desconocido_levanta_keyerror():
    with pytest.raises(KeyError):
        registry.get("block.camera").param("no_existe")


def test_duplicado_rechazado():
    from visionstudio.blocks import BlockRegistry
    from visionstudio.blocks.specs import ALL_BLOCKS

    with pytest.raises(ValueError):
        BlockRegistry((*ALL_BLOCKS[:1],) + ALL_BLOCKS[:1])