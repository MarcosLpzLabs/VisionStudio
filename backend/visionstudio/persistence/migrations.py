"""Registro de migraciones de proyectos (fase 9).

Cuando el formato de proyecto cambia (p. ej. al añadir multi-cámara en el
futuro), los archivos guardados con versiones antiguas deben poder cargarse.
Cada migración es una transformación pura `dict -> dict` que convierte un
proyecto de una versión `N` a la siguiente `N+1`.

Reglas (docs/ARQUITECTURA.md §7 y docs/FORMATO_PROYECTO.md):
- Las migraciones se registran por versión ORIGEN: `migrate_vN_to_vN+1`.
- Al cargar un proyecto antiguo se encadenan en orden hasta la versión actual.
- Si una migración falla (o no existe), se lanza ERR_MIGRATION_FAILED y el
  proyecto se rechaza: nunca se carga un archivo migrado a medias.

La versión actual del formato es 1, por lo que el registro global va VACÍO en
producción. Las migraciones reales (v1 -> v2, ...) se añadirán cuando el
formato cambie. La infraestructura queda probada con migraciones ficticias en
los tests.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from visionstudio.errors import EngineError, ErrorCode

# Una migración recibe el dict del proyecto y devuelve el dict migrado (una
# versión más). Debe ser pura: sin estado y sin efectos secundarios, para que
# el encadenamiento sea determinista y reejecutable.
MigrationFn = Callable[[dict[str, Any]], dict[str, Any]]


class MigrationRegistry:
    """Registro de migraciones `vN -> vN+1`.

    `apply(data, from_version, to_version)` encadena las migraciones
    disponibles de `from_version` hasta `to_version` (exclusivo). Si en algún
    salto no hay migración registrada o esta falla, lanza ERR_MIGRATION_FAILED
    (el error lleva la versión origen y el mensaje interno para depurar).
    """

    def __init__(self) -> None:
        # Índice: version_origen -> (version_destino, fn).
        self._migrations: dict[int, tuple[int, MigrationFn]] = {}

    def register(self, from_version: int, to_version: int, fn: MigrationFn) -> None:
        """Registra la migración que lleva de `from_version` a `to_version`.

        Debe ir EXACTAMENTE una versión hacia delante (vN -> vN+1); saltos de
        varias versiones romperían el encadenamiento y se rechazan al registrar.
        """
        if to_version != from_version + 1:
            raise ValueError(
                f"la migración debe ir una versión hacia delante: v{from_version} -> v{to_version}"
            )
        if from_version in self._migrations:
            # Registrar dos migraciones para la misma versión origen es un bug.
            raise ValueError(f"migración duplicada desde la versión v{from_version}")
        self._migrations[from_version] = (to_version, fn)

    def apply(self, data: dict[str, Any], from_version: int, to_version: int) -> dict[str, Any]:
        """Encadena las migraciones desde `from_version` hasta `to_version`.

        Devuelve el dict migrado. No modifica `data` (cada paso devuelve un
        dict nuevo), de modo que un fallo no deja el proyecto a medias.
        """
        result = data
        version = from_version
        while version < to_version:
            step = self._migrations.get(version)
            if step is None:
                raise EngineError(
                    ErrorCode.MIGRATION_FAILED,
                    {"from_version": version, "to_version": version + 1, "detail": "missing_migration"},
                )
            next_version, fn = step
            try:
                result = fn(result)
            except EngineError:
                # Una migración puede lanzar EngineError controlado; se deja pasar.
                raise
            except Exception as exc:
                # Fallo imprevisto dentro de la migración: se envuelve con
                # contexto (versión) para que no se pierda información.
                raise EngineError(
                    ErrorCode.MIGRATION_FAILED,
                    {"from_version": version, "to_version": next_version, "detail": str(exc)},
                )
            # El dict devuelto debe seguir declarando su nueva versión; si la
            # migración no lo hace, es un bug de la migración.
            result = _assert_version(result, next_version)
            version = next_version
        return result


def _assert_version(data: dict[str, Any], expected: int) -> dict[str, Any]:
    """Comprueba que la migración declaró correctamente su versión destino."""
    actual = data.get("format_version")
    if actual != expected:
        raise EngineError(
            ErrorCode.MIGRATION_FAILED,
            {"from_version": expected - 1, "to_version": expected, "detail": f"bad_result_version:{actual}"},
        )
    return data


# Instancia global usada por la capa de persistencia (project.py). En
# producción no hay migraciones (formato v1); los tests registran las suyas.
MIGRATIONS = MigrationRegistry()