"""Pruebas del descubrimiento de cámaras."""

from visionstudio.camera.discovery import list_cameras
from tests.fakes import FakeCaptureFactory, synthetic_frame


def test_lista_camaras_detectadas():
    factory = FakeCaptureFactory(open_indices=[0, 2])
    cameras = list_cameras(capture_factory=factory)

    assert [c.index for c in cameras] == [0, 2]
    assert all(c.name for c in cameras)


def test_sondeo_respeta_max_index():
    factory = FakeCaptureFactory(open_indices=[0, 3, 5])
    cameras = list_cameras(capture_factory=factory, max_index=4)

    assert [c.index for c in cameras] == [0, 3]


def test_sondeo_libera_todas_las_camaras():
    factory = FakeCaptureFactory(open_indices=[0, 2])
    list_cameras(capture_factory=factory, max_index=3)

    # Todas las instancias creadas durante el sondeo deben quedar liberadas,
    # incluidas las que no respondieron (no dejar fugas tras listar).
    assert len(factory.instances) == 3
    assert all(inst.released for inst in factory.instances)


def test_read_probe_excluye_camaras_sin_frames():
    factory = FakeCaptureFactory(open_indices=[0, 1], frames={0: [synthetic_frame()]})
    cameras = list_cameras(capture_factory=factory, read_probe=True)

    # La cámara 1 está "abierta" pero sin frames: el sondeo por lectura la excluye.
    assert [c.index for c in cameras] == [0]


def test_sin_camaras_devuelve_lista_vacia():
    factory = FakeCaptureFactory(open_indices=[])
    assert list_cameras(capture_factory=factory) == []