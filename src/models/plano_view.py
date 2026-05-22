"""
PlanoView (Fase 5.5): vista de lectura del modelo nuevo (planos +
archivos) para el dashboard.

Antes, `SQLitePlanosController.get_all_documents` devolvia
SQLiteDocument leyendo de la tabla legacy `documents`. Resultado: para
proyectos creados despues del refactor (Fase 2), el dashboard mostraba
"Total: 0 documentos" porque esos proyectos solo tienen filas en la
tabla `planos` nueva, no en `documents`.

Esta clase corrige ese mismatch: lee de `planos` (fuente de verdad de
"que planos forman parte del proyecto" segun el nuevo modelo) y hace
un join logico con `archivos` para poblar version/fecha/autor/notas
del archivo mas reciente subido para cada plano.

Mantiene una API equivalente a `SQLiteDocument` en los atributos que
consume `planos_dashboard.py`, para que el dashboard no necesite
adaptarse: doc.name, doc.id, doc.current_state (alias de doc.estado),
doc.current_version, doc.autor, doc.rev_tecnica, doc.rev_gerencia,
doc.creation_date, doc.latest_notes, doc.file_paths, doc.entries,
doc.project_phase, doc.associated_dwg, doc.codigo, doc.tipo_archivo,
doc.get_state_display_name().

Los controllers de subida actuales siguen escribiendo al sistema
legacy (documents/document_entries). La Fase 6/7 los reescribira para
que toquen planos+archivos directamente. Mientras tanto,
`bridge_legacy_uploads` (utils/database/migrations.py) cubre la grieta
trasladando cualquier upload legacy huerfana al modelo nuevo de forma
idempotente.
"""

from __future__ import annotations

from typing import List, Optional, Any
from pydantic import BaseModel, Field, ConfigDict

from models.document import DocumentEntry


class PlanoView(BaseModel):
    """
    Representacion de un plano para el dashboard. Solo lectura; los
    cambios se aplican via los servicios/controllers correspondientes
    (project_edit_service para revert, futuros servicios de subida
    para nuevas versiones).

    Los campos imitan los nombres de SQLiteDocument para que el
    dashboard no necesite ramas distintas segun el origen.
    """

    # Permite asignar atributos dinamicos sin error (compat con codigo
    # que hace setattr(doc, 'X', Y) para enriquecimientos puntuales).
    model_config = ConfigDict(extra="allow")

    # Identidad y metadatos del plano (tabla `planos`).
    db_id: int                              # planos.id (uso interno)
    name: str                               # planos.codigo (iid del Treeview)
    codigo: str                             # planos.codigo
    nombre: str                             # planos.nombre
    obligatorio: bool = False
    orden: int = 0
    estado: str = "GRIS"                    # planos.estado (Fase 5)
    tipo_archivo: str = ""
    project_phase: str = "Implantación"     # planos.fase_requerida
    rev_tecnica: str = ""                   # planos.revision_tecnica
    rev_gerencia: str = ""                  # planos.revision_gerencia

    # Snapshot del archivo mas reciente vinculado (tabla `archivos`).
    # Vacios si el plano aun no tiene ninguna subida.
    current_version: str = ""
    autor: str = ""
    creation_date: str = ""
    latest_notes: str = ""

    # Listas derivadas de archivos (todas las versiones, mas reciente primero).
    file_paths: List[str] = Field(default_factory=list)
    entries: List[DocumentEntry] = Field(default_factory=list)

    # Campo sin contrapartida en la tabla nueva. Se mantiene vacio para
    # compat con _get_referencias_status() y otros consumidores que
    # consultan associated_dwg via getattr.
    associated_dwg: str = ""

    @property
    def id(self) -> str:
        """Compat con SQLiteDocument.id (alias del name)."""
        return self.name

    @property
    def current_state(self) -> str:
        """
        Compat con SQLiteDocument.current_state. En el modelo nuevo el
        estado vive directamente en planos.estado (no derivado del
        ultimo entry), asi que devolvemos doc.estado.
        """
        return self.estado

    def get_state_display_name(self, state: Optional[str] = None) -> str:
        """
        Compat con SQLiteDocument.get_state_display_name. El filtro por
        estado del dashboard usa STATE_DISPLAY_NAMES (sistema legacy)
        actualmente; mantenemos el contrato para no romperlo. Cuando el
        filtro se reescriba (fase posterior) lo redirigimos a
        utils.estados.ESTADO_A_NOMBRE.
        """
        from models.plano_document import STATE_DISPLAY_NAMES
        state_to_check = state or self.estado
        return STATE_DISPLAY_NAMES.get(state_to_check, state_to_check)

    @classmethod
    def load_all_for_project(cls, db_manager: Any) -> List["PlanoView"]:
        """
        Lee todos los planos del proyecto y, para cada uno, sus archivos
        ordenados por fecha descendente. Construye una PlanoView por
        plano poblando los campos de archivo desde el mas reciente.

        Implementacion: 2 queries simples (N+1 deliberado). Para
        proyectos de hasta cientos de planos el coste es despreciable y
        la legibilidad/debug es mejor que con window functions.
        """
        with db_manager.connection() as conn:
            planos_rows = conn.execute(
                """
                SELECT id, codigo, nombre, tipo_archivo, obligatorio,
                       orden, estado, fase_requerida, version, autor,
                       revision_tecnica, revision_gerencia
                FROM planos
                ORDER BY obligatorio DESC, orden ASC, id ASC
                """
            ).fetchall()

            result: List[PlanoView] = []
            for prow in planos_rows:
                plano_id = prow["id"]

                archivos_rows = conn.execute(
                    """
                    SELECT id, version, autor, fecha, comentarios,
                           ruta_archivo
                    FROM archivos
                    WHERE plano_id = ?
                    ORDER BY fecha DESC, id DESC
                    """,
                    (plano_id,),
                ).fetchall()

                # Construir entries (compat con el modal de historial,
                # que itera doc.entries y lee version/state/author/...).
                # Usamos el estado actual del plano como `state` de cada
                # entry porque el modelo nuevo no asocia estado a cada
                # subida (las transiciones se rastrean en
                # plano_estado_historial, no en archivos).
                entries: List[DocumentEntry] = []
                file_paths: List[str] = []
                for arow in archivos_rows:
                    entries.append(DocumentEntry(
                        version=arow["version"] or "",
                        state=prow["estado"],
                        timestamp=str(arow["fecha"]) if arow["fecha"] else "",
                        author=arow["autor"] or "",
                        notes=arow["comentarios"] or "",
                        file_path=arow["ruta_archivo"] or None,
                    ))
                    if arow["ruta_archivo"]:
                        file_paths.append(arow["ruta_archivo"])

                # Snapshot del archivo mas reciente (primera fila por el
                # ORDER BY fecha DESC).
                if archivos_rows:
                    latest = archivos_rows[0]
                    current_version = latest["version"] or ""
                    autor = latest["autor"] or (prow["autor"] or "")
                    creation_date = str(latest["fecha"]) if latest["fecha"] else ""
                    latest_notes = latest["comentarios"] or ""
                else:
                    # Sin archivos: caer a los campos denormalizados de
                    # planos (poblados por servicios de subida cuando
                    # los reescribamos en Fase 6/7).
                    current_version = prow["version"] or ""
                    autor = prow["autor"] or ""
                    creation_date = ""
                    latest_notes = ""

                result.append(cls(
                    db_id=plano_id,
                    name=prow["codigo"],
                    codigo=prow["codigo"],
                    nombre=prow["nombre"],
                    obligatorio=bool(prow["obligatorio"]),
                    orden=prow["orden"],
                    estado=prow["estado"] or "GRIS",
                    tipo_archivo=prow["tipo_archivo"] or "",
                    project_phase=prow["fase_requerida"] or "Implantación",
                    rev_tecnica=prow["revision_tecnica"] or "",
                    rev_gerencia=prow["revision_gerencia"] or "",
                    current_version=current_version,
                    autor=autor,
                    creation_date=creation_date,
                    latest_notes=latest_notes,
                    file_paths=file_paths,
                    entries=entries,
                ))

        return result
