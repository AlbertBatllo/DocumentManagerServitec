"""
Servicio de edicion de proyectos (Fase 3).

Paralelo a `project_creation_service.py`. Orquesta la edicion de un
proyecto existente:

    1. Carga de datos actuales (proyecto + planos ordenados).
    2. Comprobacion de seguridad al borrar un plano (existencia de
       archivos asociados y/o registros en plano_estado_historial).
    3. Aplicacion del batch de cambios dentro de una unica transaccion:
        - UPDATE de la fila en `proyectos`.
        - UPDATE de nombres / codigos de planos existentes.
        - INSERT de detalles nuevos con estado='GRIS'.
        - DELETE de planos marcados para borrado (CASCADE elimina
          archivos e historial).
        - UPDATE de estado al estado anterior de planos marcados para
          'recuperar estado anterior' (sin borrar arxius).
        - REGISTRO en plano_estado_historial de cualquier cambio de
          estado, para mantener trazabilidad.

Decision Fase 3: el codigo del proyecto NO se puede cambiar desde el
formulario de edicion. Esto elimina la necesidad de renombrar la carpeta
en disco, cerrar la BD y manejar rollback de I/O. La complejidad queda
acotada a operaciones SQL.
"""

import sqlite3
from pathlib import Path
from typing import Optional

from utils.database.project_database_manager import ensure_project_database


class ProjectEditError(Exception):
    """Error en el proceso de edicion de un proyecto."""


def load_project_for_edit(project_path: Path) -> dict:
    """
    Lee la fila de `proyectos` y todos los planos del proyecto, ordenados
    por `orden`.

    Returns:
        dict con claves:
            - id, codigo, nombre, tipo, lugar, descripcion
            - planos: lista de dicts con
                {id, codigo, nombre, obligatorio, orden, estado}
              ordenada por (obligatorio DESC, orden ASC) para que los
              obligatorios aparezcan primero en el formulario.
    """
    project_path = Path(project_path)
    db_manager = ensure_project_database(project_path)

    with db_manager.connection() as conn:
        proyecto_row = conn.execute(
            "SELECT id, codigo, nombre, tipo, lugar, descripcion "
            "FROM proyectos LIMIT 1"
        ).fetchone()
        if proyecto_row is None:
            raise ProjectEditError(
                f"No se encontro ninguna fila en `proyectos` para {project_path}."
            )

        planos_rows = conn.execute(
            "SELECT id, codigo, nombre, obligatorio, orden, estado "
            "FROM planos "
            "ORDER BY obligatorio DESC, orden ASC, id ASC"
        ).fetchall()

    return {
        "id": proyecto_row["id"],
        "codigo": proyecto_row["codigo"],
        "nombre": proyecto_row["nombre"],
        "tipo": proyecto_row["tipo"] or "OBRA_NUEVA",
        "lugar": proyecto_row["lugar"] or "",
        "descripcion": proyecto_row["descripcion"] or "",
        "planos": [
            {
                "id": r["id"],
                "codigo": r["codigo"],
                "nombre": r["nombre"],
                "obligatorio": bool(r["obligatorio"]),
                "orden": r["orden"],
                "estado": r["estado"],
            }
            for r in planos_rows
        ],
    }


def check_delete_safety(project_path: Path, plano_id: int) -> str:
    """
    Determina la severidad del borrado de un plano para decidir que
    dialogo mostrar al usuario.

    Returns:
        "safe": el plano no tiene archivos asociados ni historial.
                Confirmacion simple es suficiente.
        "no_history": tiene archivos pero ningun registro en
                      plano_estado_historial. Confirmacion destructiva.
        "has_history": tiene archivos Y al menos un registro de cambio
                       de estado. Dialogo de 3 opciones (recuperar
                       estado anterior / borrar / cancelar).
    """
    project_path = Path(project_path)
    db_manager = ensure_project_database(project_path)

    with db_manager.connection() as conn:
        archivos = conn.execute(
            "SELECT COUNT(*) AS c FROM archivos WHERE plano_id = ?",
            (plano_id,),
        ).fetchone()
        n_archivos = archivos["c"] if archivos else 0

        if n_archivos == 0:
            return "safe"

        historial = conn.execute(
            "SELECT COUNT(*) AS c FROM plano_estado_historial WHERE plano_id = ?",
            (plano_id,),
        ).fetchone()
        n_historial = historial["c"] if historial else 0

    return "has_history" if n_historial > 0 else "no_history"


def _get_previous_state(conn: sqlite3.Connection, plano_id: int) -> Optional[str]:
    """
    Devuelve el `estado_anterior` del ultimo registro de historial para
    este plano, o None si no hay historial o el ultimo registro no tiene
    estado anterior (caso plano recien creado).
    """
    row = conn.execute(
        "SELECT estado_anterior FROM plano_estado_historial "
        "WHERE plano_id = ? "
        "ORDER BY cambiado_en DESC, id DESC "
        "LIMIT 1",
        (plano_id,),
    ).fetchone()
    if row is None:
        return None
    return row["estado_anterior"]


def editar_proyecto(project_path: Path, form_data: dict) -> None:
    """
    Aplica el batch completo de cambios definido por el formulario de
    edicion. Todo dentro de una unica transaccion: si algo falla, no se
    persiste ningun cambio.

    Args:
        project_path: ruta de la carpeta del proyecto (no cambia).
        form_data: dict con la siguiente forma esperada del view:
            {
                "tipo": "OBRA_NUEVA" | "REFORMA",
                "nombre": str,
                "lugar": str,
                "descripcion": str,
                "planos_existentes": [
                    {"id": int, "nombre": str, "codigo": str},
                    ...
                ],
                "planos_nuevos_detalle": [str, ...],
                "planos_a_borrar": [int, ...],
                "planos_a_revertir": [int, ...],
            }

    Raises:
        ProjectEditError: para errores de validacion o de BD. La
            transaccion se hace rollback automaticamente.
    """
    tipo = form_data.get("tipo")
    nombre = (form_data.get("nombre") or "").strip()
    lugar = (form_data.get("lugar") or "").strip() or None
    descripcion = (form_data.get("descripcion") or "").strip() or None

    if tipo not in ("OBRA_NUEVA", "REFORMA"):
        raise ProjectEditError(f"Tipo invalido: {tipo!r}.")
    if not nombre:
        raise ProjectEditError("El nombre del proyecto es obligatorio.")

    planos_existentes = form_data.get("planos_existentes") or []
    planos_nuevos = [
        n.strip() for n in (form_data.get("planos_nuevos_detalle") or []) if n.strip()
    ]
    planos_a_borrar = set(form_data.get("planos_a_borrar") or [])
    planos_a_revertir = set(form_data.get("planos_a_revertir") or [])

    # Si un plano esta marcado a la vez como borrar y revertir, prevalece
    # borrar (interpretacion: el ultimo gesto del usuario gana, y el
    # borrado es destructivo y mas definitivo que el revert).
    planos_a_revertir -= planos_a_borrar

    project_path = Path(project_path)
    db_manager = ensure_project_database(project_path)

    try:
        with db_manager.transaction() as conn:
            # 1. UPDATE proyecto
            conn.execute(
                """
                UPDATE proyectos
                SET tipo = ?,
                    nombre = ?,
                    lugar = ?,
                    descripcion = ?,
                    modificado_en = CURRENT_TIMESTAMP
                """,
                (tipo, nombre, lugar, descripcion),
            )

            # 2. UPDATE de planos existentes (nombre + codigo).
            for plano in planos_existentes:
                pid = plano.get("id")
                if pid is None:
                    continue
                if pid in planos_a_borrar:
                    continue
                nuevo_nombre = (plano.get("nombre") or "").strip()
                nuevo_codigo = (plano.get("codigo") or nuevo_nombre).strip()
                if not nuevo_nombre:
                    raise ProjectEditError(
                        f"El nombre del plano id={pid} no puede estar vacio."
                    )
                conn.execute(
                    "UPDATE planos SET nombre = ?, codigo = ? WHERE id = ?",
                    (nuevo_nombre, nuevo_codigo, pid),
                )

            # 3. INSERT de detalles nuevos. El `orden` continua despues
            #    del maximo actual para no colisionar con los existentes.
            if planos_nuevos:
                row = conn.execute(
                    "SELECT COALESCE(MAX(orden), 0) AS max_orden FROM planos"
                ).fetchone()
                next_orden = (row["max_orden"] if row else 0) + 1

                proyecto_row = conn.execute(
                    "SELECT id FROM proyectos LIMIT 1"
                ).fetchone()
                if proyecto_row is None:
                    raise ProjectEditError(
                        "No existe fila de proyectos para asociar planos nuevos."
                    )
                proyecto_id = proyecto_row["id"]

                for nom in planos_nuevos:
                    conn.execute(
                        """
                        INSERT INTO planos
                        (proyecto_id, codigo, nombre, obligatorio, orden, estado)
                        VALUES (?, ?, ?, 0, ?, 'GRIS')
                        """,
                        (proyecto_id, nom, nom, next_orden),
                    )
                    next_orden += 1

            # 4. Revertir estado de planos marcados. Solo si hay
            #    estado_anterior disponible en el historial; si no, se
            #    deja como esta y se anota en logs sin abortar.
            for pid in planos_a_revertir:
                estado_anterior = _get_previous_state(conn, pid)
                if estado_anterior is None:
                    # No hay donde revertir; silenciosamente ignorar.
                    continue
                # Estado actual para registrar transicion.
                actual_row = conn.execute(
                    "SELECT estado FROM planos WHERE id = ?", (pid,)
                ).fetchone()
                if actual_row is None:
                    continue
                estado_actual = actual_row["estado"]
                if estado_actual == estado_anterior:
                    continue
                conn.execute(
                    "UPDATE planos SET estado = ? WHERE id = ?",
                    (estado_anterior, pid),
                )
                conn.execute(
                    """
                    INSERT INTO plano_estado_historial
                    (plano_id, estado_anterior, estado_nuevo)
                    VALUES (?, ?, ?)
                    """,
                    (pid, estado_actual, estado_anterior),
                )

            # 5. DELETE de planos. ON DELETE CASCADE en `archivos` y
            #    `plano_estado_historial` se encarga del resto.
            for pid in planos_a_borrar:
                conn.execute("DELETE FROM planos WHERE id = ?", (pid,))

    except ProjectEditError:
        raise
    except sqlite3.Error as exc:
        raise ProjectEditError(f"Error de base de datos: {exc}") from exc
    except Exception as exc:  # pragma: no cover - safety net
        raise ProjectEditError(f"Error inesperado: {exc}") from exc
