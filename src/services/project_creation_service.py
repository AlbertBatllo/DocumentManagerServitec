"""
Servicio de creacion de proyectos (Fase 2).

Orquesta:
    1. Validacion de los datos del formulario.
    2. Creacion fisica de la carpeta del proyecto en
       `get_projects_root()`.
    3. Inicializacion de la BD via `ensure_project_database`, que dispara
       la migracion de Fase 1 y crea las 4 tablas nuevas + 1 fila en
       `proyectos`.
    4. UPDATE de la fila auto-creada con los datos del formulario.
    5. INSERT de los planos obligatorios y de detalles, todos con
       estado='GRIS'.
    6. Rollback (rmtree de la carpeta) si algo falla a mitad.

El servicio reutiliza la logica de creacion de esquema existente para no
duplicar SQL.
"""

import shutil
from pathlib import Path
from typing import List, Optional

from utils.app_paths import get_projects_root
from utils.database.project_database_manager import ensure_project_database


PROJECT_CODE_PREFIX = "PRJ-"


class ProjectCreationError(Exception):
    """Error en el proceso de creacion de un proyecto."""


class ProjectAlreadyExistsError(ProjectCreationError):
    """La carpeta del proyecto ya existe en el sistema de archivos."""


def normalize_code(raw_code: str) -> str:
    """
    Aplica el prefijo PRJ- al codigo introducido por el usuario.

    - Si el usuario ya escribio PRJ-XYZ, no se duplica el prefijo.
    - Se eliminan espacios al inicio y final.
    - Se rechaza si tras normalizar queda solo el prefijo (vacio).
    """
    cleaned = (raw_code or "").strip()
    if not cleaned:
        raise ProjectCreationError("El codigo no puede estar vacio.")

    if cleaned.upper().startswith(PROJECT_CODE_PREFIX):
        # Normalizar a mayusculas en el prefijo conservando el resto.
        cleaned = PROJECT_CODE_PREFIX + cleaned[len(PROJECT_CODE_PREFIX):]
    else:
        cleaned = PROJECT_CODE_PREFIX + cleaned

    if cleaned == PROJECT_CODE_PREFIX:
        raise ProjectCreationError("El codigo solo contiene el prefijo PRJ-.")

    return cleaned


def crear_proyecto(
    tipo: str,
    nombre: str,
    codigo: str,
    lugar: Optional[str],
    descripcion: Optional[str],
    obligatorios: List[str],
    detalles: List[str],
) -> Path:
    """
    Crea fisicamente un proyecto nuevo y persiste sus datos en la BD.

    Args:
        tipo: 'OBRA_NUEVA' o 'REFORMA'.
        nombre: Nombre legible del proyecto.
        codigo: Codigo introducido por el usuario (sin necesidad del
                prefijo PRJ-, se normaliza automaticamente).
        lugar: Lugar / ubicacion (opcional).
        descripcion: Descripcion libre (opcional).
        obligatorios: Lista ordenada de nombres de planos obligatorios.
        detalles: Lista ordenada de nombres de planos de tipo detalle.

    Returns:
        Path absoluto de la carpeta del proyecto creada.

    Raises:
        ProjectAlreadyExistsError: si ya existe carpeta con ese codigo.
        ProjectCreationError: para errores de validacion o de I/O.
    """
    # Validaciones basicas
    if tipo not in ("OBRA_NUEVA", "REFORMA"):
        raise ProjectCreationError(f"Tipo invalido: {tipo!r}.")
    if not (nombre or "").strip():
        raise ProjectCreationError("El nombre del proyecto es obligatorio.")

    codigo_norm = normalize_code(codigo)

    root = get_projects_root()
    folder = root / codigo_norm

    if folder.exists():
        raise ProjectAlreadyExistsError(
            f"Ya existe una carpeta con el codigo '{codigo_norm}'."
        )

    # Crear la carpeta fisica. A partir de aqui, todo va envuelto en
    # try/except para rollback.
    folder.mkdir(parents=True, exist_ok=False)

    try:
        # Esto inicializa la BD y dispara apply_refactor_fase1, que
        # crea las 4 tablas nuevas e inserta una fila en `proyectos`
        # con codigo=nombre=folder.name, tipo=NULL.
        db_manager = ensure_project_database(folder)

        with db_manager.transaction() as conn:
            # Actualizar la fila auto-creada con los datos del formulario.
            conn.execute(
                """
                UPDATE proyectos
                SET tipo = ?,
                    nombre = ?,
                    lugar = ?,
                    descripcion = ?,
                    modificado_en = CURRENT_TIMESTAMP
                WHERE codigo = ?
                """,
                (tipo, nombre.strip(),
                 (lugar or "").strip() or None,
                 (descripcion or "").strip() or None,
                 codigo_norm),
            )

            row = conn.execute(
                "SELECT id FROM proyectos WHERE codigo = ?", (codigo_norm,)
            ).fetchone()
            if not row:
                raise ProjectCreationError(
                    "La fila de proyectos no se ha creado tras inicializar la BD."
                )
            proyecto_id = row["id"] if hasattr(row, "keys") else row[0]

            # Insertar planos obligatorios y detalles, en orden continuo.
            orden = 1
            for nom in obligatorios:
                conn.execute(
                    """
                    INSERT INTO planos
                    (proyecto_id, codigo, nombre, obligatorio, orden, estado)
                    VALUES (?, ?, ?, 1, ?, 'GRIS')
                    """,
                    (proyecto_id, nom, nom, orden),
                )
                orden += 1
            for nom in detalles:
                conn.execute(
                    """
                    INSERT INTO planos
                    (proyecto_id, codigo, nombre, obligatorio, orden, estado)
                    VALUES (?, ?, ?, 0, ?, 'GRIS')
                    """,
                    (proyecto_id, nom, nom, orden),
                )
                orden += 1

        db_manager.close_connection()
        return folder

    except Exception as exc:
        # Rollback: borrar todo lo creado en disco.
        try:
            shutil.rmtree(folder, ignore_errors=True)
        finally:
            if isinstance(exc, ProjectCreationError):
                raise
            raise ProjectCreationError(
                f"Error creando el proyecto: {exc}"
            ) from exc
