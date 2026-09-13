"""Re-export de los errores transversales.

Los errores viven en `visionstudio.errors` (capa transversal). Este módulo se
mantiene para no romper los imports existentes del motor
(`visionstudio.engine.errors`).
"""

from visionstudio.errors import EngineError, ErrorCode

__all__ = ["EngineError", "ErrorCode"]