"""Capa de persistencia de proyectos."""

from visionstudio.persistence.migrations import MIGRATIONS, MigrationRegistry
from visionstudio.persistence.project import (
    CURRENT_FORMAT_VERSION,
    ProjectMeta,
    project_from_dict,
    project_to_dict,
)

__all__ = [
    "CURRENT_FORMAT_VERSION",
    "MIGRATIONS",
    "MigrationRegistry",
    "ProjectMeta",
    "project_from_dict",
    "project_to_dict",
]