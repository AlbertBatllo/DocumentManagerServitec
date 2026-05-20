"""
Migraciones idempotentes del esquema de la BD por proyecto.

Estado actual del esquema (pre-refactor):
    - documents (TABLE, 23 columnas, document_type='planos' es el unico tipo usado)
    - document_entries (TABLE, historial de versiones, FK -> documents)
    - planos (VIEW sobre documents WHERE document_type='planos')
    - schema_version (TABLE, ultima version registrada: '2.0.0')
    - document_locks (TABLE, opcional)

Esta migracion (refactor fase 1) introduce el nuevo modelo descrito en
REFACTOR_PLAN.md seccion 5, en paralelo a las tablas legacy (que no se
borran, para permitir rollback trivial).

Cambios:
    - DROP VIEW planos (colisiona con la nueva TABLE planos).
    - CREATE TABLE proyectos / planos / archivos / plano_estado_historial.
    - Copia de datos: documents -> planos, document_entries -> archivos.
    - INSERT en schema_version con marker '3.0.0-refactor-fase1'.

Desviaciones respecto al pla:
    - proyectos.tipo se define como NULLABLE (CHECK admite NULL) porque los
      proyectos migrados no tienen tipo asignado y el usuario decidio dejarlo
      vacio hasta que se edite desde la UI (Fase 3).

Backup automatico:
    Antes de aplicar cambios destructivos se crea
    'documents.db.backup_pre_refactor_fase1_<timestamp>' en la misma carpeta
    via SQLite VACUUM INTO (consistente y seguro con la conexion abierta).

Rollback (manual, documentado):
    1. Cerrar la app.
    2. Restaurar el backup: copiar
       'documents.db.backup_pre_refactor_fase1_<ts>' sobre 'documents.db'.
    Alternativamente, manteniendo el .db actual:
        DROP TABLE plano_estado_historial;
        DROP TABLE archivos;
        DROP TABLE planos;
        DROP TABLE proyectos;
        DELETE FROM schema_version WHERE version='3.0.0-refactor-fase1';
        CREATE VIEW planos AS
            SELECT id, name, current_version as version, current_state as state,
                   autor, rev_tecnica, rev_gerencia, created_at, updated_at,
                   plano_type, xref_references, xref_processing_status,
                   xref_method_used, xref_last_processed, is_master, nivel,
                   master_plano_id, associated_dwg, file_paths
            FROM documents WHERE document_type='planos';
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional


MIGRATION_VERSION = "3.0.0-refactor-fase1"

# Mapeo de estados legacy -> nuevos estados (REFACTOR_PLAN.md seccion 3).
# Decisiones confirmadas por el usuario: S0->BLANCO, S1->S1, S2->S2.
_STATE_MAP = {
    "S0": "BLANCO",
    "S1": "S1",
    "S2": "S2",
    "":   "GRIS",   # sin estado -> pendiente
    None: "GRIS",
}


def _is_already_applied(conn: sqlite3.Connection) -> bool:
    """Devuelve True si la migracion fase 1 ya esta aplicada."""
    try:
        cur = conn.execute(
            "SELECT 1 FROM schema_version WHERE version = ? LIMIT 1",
            (MIGRATION_VERSION,),
        )
        return cur.fetchone() is not None
    except sqlite3.OperationalError:
        # schema_version puede no existir en BDs muy antiguas; en ese caso
        # tampoco esta aplicada esta migracion.
        return False


def _ensure_schema_version_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_version (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            version TEXT NOT NULL,
            applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)


def _backup_database(db_path: Path) -> Optional[Path]:
    """
    Crea un backup consistente del .db via VACUUM INTO.

    Devuelve el Path del backup, o None si no hay BD que respaldar.
    VACUUM INTO requiere su propia conexion y NO puede ejecutarse dentro de
    una transaccion abierta, por eso abrimos una conexion dedicada y la
    cerramos antes de seguir.
    """
    if not db_path.exists():
        return None

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.with_name(
        f"{db_path.name}.backup_pre_refactor_fase1_{timestamp}"
    )

    # Conexion dedicada para el backup.
    backup_conn = sqlite3.connect(str(db_path))
    try:
        backup_conn.execute(f"VACUUM INTO '{str(backup_path).replace(chr(39), chr(39)*2)}'")
        backup_conn.commit()
    finally:
        backup_conn.close()

    return backup_path


def _create_new_tables(conn: sqlite3.Connection) -> None:
    """Crea las cuatro tablas nuevas con sus indices."""

    conn.execute("""
        CREATE TABLE proyectos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT NOT NULL UNIQUE,
            nombre TEXT NOT NULL,
            tipo TEXT CHECK(tipo IS NULL OR tipo IN ('OBRA_NUEVA', 'REFORMA')),
            lugar TEXT,
            descripcion TEXT,
            ruta_carpeta TEXT NOT NULL,
            creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modificado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.execute("""
        CREATE TABLE planos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            proyecto_id INTEGER NOT NULL,
            codigo TEXT NOT NULL,
            nombre TEXT NOT NULL,
            tipo_archivo TEXT,
            obligatorio INTEGER NOT NULL DEFAULT 0,
            orden INTEGER NOT NULL DEFAULT 0,
            estado TEXT NOT NULL DEFAULT 'GRIS'
                CHECK(estado IN ('GRIS','BLANCO','S1','S2','S3','ROJO','NARANJA')),
            version TEXT,
            fase_requerida TEXT,
            fecha TIMESTAMP,
            autor TEXT,
            revision_tecnica TEXT,
            revision_gerencia TEXT,
            FOREIGN KEY (proyecto_id) REFERENCES proyectos(id) ON DELETE CASCADE
        )
    """)

    conn.execute("""
        CREATE TABLE archivos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plano_id INTEGER NOT NULL,
            version TEXT NOT NULL,
            autor TEXT,
            fecha TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            comentarios TEXT,
            motivo_subida TEXT,
            ruta_archivo TEXT NOT NULL,
            FOREIGN KEY (plano_id) REFERENCES planos(id) ON DELETE CASCADE
        )
    """)

    conn.execute("""
        CREATE TABLE plano_estado_historial (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plano_id INTEGER NOT NULL,
            estado_anterior TEXT,
            estado_nuevo TEXT NOT NULL,
            cambiado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (plano_id) REFERENCES planos(id) ON DELETE CASCADE
        )
    """)

    conn.execute("CREATE INDEX idx_planos_proyecto ON planos(proyecto_id)")
    conn.execute("CREATE INDEX idx_archivos_plano ON archivos(plano_id)")
    conn.execute("CREATE INDEX idx_historial_plano ON plano_estado_historial(plano_id)")


def _legacy_planos_table_exists(conn: sqlite3.Connection) -> bool:
    """True si existe la tabla legacy 'documents' con planos para migrar."""
    cur = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='documents' LIMIT 1"
    )
    return cur.fetchone() is not None


def _migrate_data(conn: sqlite3.Connection, project_path: Path) -> dict:
    """
    Vuelca datos de las tablas legacy a las nuevas.

    Devuelve un dict con conteos para verificacion.
    """
    counts = {
        "planos_legacy": 0,
        "planos_migrados": 0,
        "archivos_legacy": 0,
        "archivos_migrados": 0,
        "proyectos_creados": 0,
    }

    # 1. Crear la fila unica en `proyectos` representando este proyecto.
    project_code = project_path.name
    project_name = project_path.name
    ruta_carpeta = str(project_path.resolve())

    # Intentar inferir creado_en a partir del documento mas antiguo si existe.
    creado_en = None
    if _legacy_planos_table_exists(conn):
        cur = conn.execute(
            "SELECT MIN(created_at) FROM documents WHERE document_type='planos'"
        )
        row = cur.fetchone()
        creado_en = row[0] if row and row[0] else None

    if creado_en:
        conn.execute(
            """INSERT INTO proyectos
               (codigo, nombre, tipo, ruta_carpeta, creado_en, modificado_en)
               VALUES (?, ?, NULL, ?, ?, CURRENT_TIMESTAMP)""",
            (project_code, project_name, ruta_carpeta, creado_en),
        )
    else:
        conn.execute(
            """INSERT INTO proyectos
               (codigo, nombre, tipo, ruta_carpeta)
               VALUES (?, ?, NULL, ?)""",
            (project_code, project_name, ruta_carpeta),
        )
    proyecto_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    counts["proyectos_creados"] = 1

    # Si no hay tabla legacy, nada mas que hacer.
    if not _legacy_planos_table_exists(conn):
        return counts

    # 2. Migrar documents (tipo planos) -> planos
    legacy_rows = conn.execute("""
        SELECT id, name, current_version, current_state,
               autor, rev_tecnica, rev_gerencia,
               project_phase, file_type, updated_at
        FROM documents
        WHERE document_type='planos'
        ORDER BY id
    """).fetchall()
    counts["planos_legacy"] = len(legacy_rows)

    for orden, row in enumerate(legacy_rows, start=1):
        (doc_id, name, version, state, autor,
         rev_tec, rev_ger, phase, file_type, updated_at) = row

        estado_nuevo = _STATE_MAP.get(state, "GRIS")

        # Insertar preservando el id original para que document_entries
        # apunten al mismo plano_id sin necesidad de mapeo extra.
        conn.execute("""
            INSERT INTO planos
            (id, proyecto_id, codigo, nombre, tipo_archivo, obligatorio,
             orden, estado, version, fase_requerida, fecha, autor,
             revision_tecnica, revision_gerencia)
            VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            doc_id,
            proyecto_id,
            name,           # codigo = name (decision usuario)
            name,           # nombre = name
            file_type or None,
            orden,
            estado_nuevo,
            version or None,
            phase or None,
            updated_at,
            autor or None,
            rev_tec or None,
            rev_ger or None,
        ))
        counts["planos_migrados"] += 1

    # 3. Migrar document_entries -> archivos
    legacy_entries = conn.execute("""
        SELECT id, document_id, version, author, timestamp,
               notes, file_path
        FROM document_entries
        WHERE document_id IN (
            SELECT id FROM documents WHERE document_type='planos'
        )
        ORDER BY id
    """).fetchall()
    counts["archivos_legacy"] = len(legacy_entries)

    for entry in legacy_entries:
        (entry_id, doc_id, version, author, ts, notes, file_path) = entry
        conn.execute("""
            INSERT INTO archivos
            (id, plano_id, version, autor, fecha, comentarios,
             motivo_subida, ruta_archivo)
            VALUES (?, ?, ?, ?, ?, ?, NULL, ?)
        """, (
            entry_id,
            doc_id,
            version or "",
            author or None,
            ts,
            notes or None,
            file_path or "",   # NOT NULL en el nuevo modelo
        ))
        counts["archivos_migrados"] += 1

    return counts


def apply_refactor_fase1(
    conn: sqlite3.Connection,
    project_path: Path,
) -> Optional[dict]:
    """
    Aplica la migracion de Fase 1 de forma idempotente.

    - Si ya esta aplicada, devuelve None.
    - Si se aplica, devuelve un dict con info de la operacion (conteos y
      path del backup).

    Atomicidad: todas las operaciones de DDL/DML se ejecutan dentro de una
    unica transaccion (savepoint). El backup se hace fuera de la transaccion
    porque VACUUM INTO no es transaccionable.
    """
    _ensure_schema_version_table(conn)
    if _is_already_applied(conn):
        return None

    db_path = Path(conn.execute("PRAGMA database_list").fetchall()[0][2])

    backup_path = _backup_database(db_path)

    # Asegurar que no hay transaccion abierta del caller; usar SAVEPOINT.
    conn.execute("SAVEPOINT refactor_fase1")
    try:
        # Eliminar la vista 'planos' que colisiona con la nueva tabla.
        conn.execute("DROP VIEW IF EXISTS planos")

        _create_new_tables(conn)
        counts = _migrate_data(conn, project_path)

        # Marcar como aplicada.
        conn.execute(
            "INSERT INTO schema_version (version) VALUES (?)",
            (MIGRATION_VERSION,),
        )

        conn.execute("RELEASE SAVEPOINT refactor_fase1")
        conn.commit()
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT refactor_fase1")
        conn.execute("RELEASE SAVEPOINT refactor_fase1")
        raise

    return {
        "version": MIGRATION_VERSION,
        "backup_path": str(backup_path) if backup_path else None,
        "counts": counts,
    }
