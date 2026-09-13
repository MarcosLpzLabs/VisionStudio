"""Registro y especificaciones de bloques.

Punto de entrada único para que el resto del backend (motor, API, pruebas)
importe el registro compartido y los modelos de especificación.
"""

from visionstudio.blocks.registry import BlockRegistry, registry
from visionstudio.blocks.specs import ALL_BLOCKS, BlockSpec, ParamSpec, PortSpec

__all__ = [
    "ALL_BLOCKS",
    "BlockRegistry",
    "BlockSpec",
    "ParamSpec",
    "PortSpec",
    "registry",
]