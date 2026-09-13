"""Pruebas del dispositivo de cámara."""

import cv2
import pytest

from visionstudio.camera.device import CameraConfig, CameraDevice
from visionstudio.errors import EngineError, ErrorCode
from tests.fakes import FakeCapture, FakeCaptureFactory, synthetic_frame


def test_abrir_camara_y_configurar_resolucion():
    factory = FakeCaptureFactory(open_indices=[0])
    device = CameraDevice(capture_factory=factory)
    config = CameraConfig(index=0, width=800, height=600)

    device.open(config)

    assert device.is_open
    assert device.config == config
    capture = factory.instance(0)
    # La resolución se aplica vía set(CAP_PROP_FRAME_*, ...).
    props = {prop for prop, _ in capture.set_calls}
    assert cv2.CAP_PROP_FRAME_WIDTH in props
    assert cv2.CAP_PROP_FRAME_HEIGHT in props


def test_abrir_camara_inexistente_lanza_camera_open():
    device = CameraDevice(capture_factory=FakeCaptureFactory(open_indices=[]))
    with pytest.raises(EngineError) as exc:
        device.open(CameraConfig(index=5))
    assert exc.value.code == ErrorCode.CAMERA_OPEN


def test_read_devuelve_frame():
    frame = synthetic_frame()
    factory = FakeCaptureFactory(open_indices=[0], frames={0: [frame]})
    device = CameraDevice(capture_factory=factory)
    device.open(CameraConfig(index=0))

    result = device.read()
    assert result is frame


def test_read_sin_camara_abierta_lanza_error():
    device = CameraDevice(capture_factory=FakeCaptureFactory(open_indices=[]))
    with pytest.raises(EngineError) as exc:
        device.read()
    assert exc.value.code == ErrorCode.CAMERA_OPEN


def test_read_sin_frames_devuelve_none():
    # Cámara abierta pero sin frames disponibles (desconectada/colgada).
    factory = FakeCaptureFactory(open_indices=[0], frames={0: []})
    device = CameraDevice(capture_factory=factory)
    device.open(CameraConfig(index=0))

    assert device.read() is None


def test_reabrir_libera_la_camara_anterior():
    factory = FakeCaptureFactory(open_indices=[0])
    device = CameraDevice(capture_factory=factory)
    device.open(CameraConfig(index=0))
    first = factory.instance(0)

    device.open(CameraConfig(index=0))  # reabrir libera la anterior

    assert first.released
    assert device.is_open


def test_release_idempotente_y_libera():
    factory = FakeCaptureFactory(open_indices=[0])
    device = CameraDevice(capture_factory=factory)
    device.open(CameraConfig(index=0))
    capture = factory.instance(0)

    device.release()
    device.release()  # segundo release: no debe fallar

    assert capture.released
    assert not device.is_open


def test_release_con_fallo_backend_lanza_camera_release():
    capture = FakeCapture(index=0, open_ok=True, release_raises=True)
    factory = lambda index: capture  # noqa: E731
    device = CameraDevice(capture_factory=factory)
    device.open(CameraConfig(index=0))

    with pytest.raises(EngineError) as exc:
        device.release()
    assert exc.value.code == ErrorCode.CAMERA_RELEASE