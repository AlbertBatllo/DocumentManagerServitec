"""
Servicio de subida individual (Fase 6).

Reescribe el flujo de subida para escribir directamente al modelo nuevo
(tablas `planos` y `archivos`), reemplazando la pila legacy que usaba
documents/document_entries.

Decision (acordada con el usuario, Fase 6):
    El boton "Registrar Nueva Version" del dashboard cubre solo el
    CASO 2 (plano existente). Para subir un plano que aun no existe
    en el proyecto, el usuario primero lo crea via "Editar proyecto"
    (Fase 3) y luego le sube la primera version.
    No obstante, este modulo expone tambien `subir_plano_nuevo` porque
    la Fase 7 (subida masiva) necesitara crear planos al vuelo a
    partir de archivos arrastrados sin contraparte definida.

Logica de version superior / inferior (REFACTOR_PLAN seccion 9.1):
    - Si la version nueva > version actual: UPDATE planos con la nueva
      version. Si el estado actual era ROJO (rechazo), pasar a S1
      (revision pendiente). En otro caso, dejar el estado tal cual.
    - Si la version nueva <= version actual o no es comparable:
      marcar planos.estado = NARANJA (version incoherente).
    - La primera subida de un plano sin version previa siempre se
      considera "superior" y dispara la transicion GRIS -> S1.

Toda transicion de estado pasa por `utils.estados.cambiar_estado`,
que actualiza `planos.estado` e inserta en `plano_estado_historial`
de forma atomica.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from typing import Optional

from utils.database.project_database_manager import ensure_project_database
from utils.estados import ESTADOS, cambiar_estado
from utils.folder_resolver import FolderResolver
from utils.version_validator import VersionValidator


class UploadError(Exception):
    """Error durante el proceso de subida."""


# Mapeo extension -> subcarpeta dentro de 02_Planos/. Coherente con la
# convencion legacy que ya existe en disco (FolderStructureManager).
_EXT_A_SUBCARPETA = {
    ".pdf": "PDF",
    ".dwg": "CAD",
    ".dxf": "CAD",
    ".rvt": "RVT",
}


def comparar_versiones(version_actual: Optional[str], version_nueva: str) -> int:
    """
    Compara dos versiones del formato `X.Y`.

    Returns:
        -1 si actual < nueva (subida superior).
         0 si actual == nueva.
         1 si actual > nueva.
        -1 si actual es None / vacio (primera subida -> tratar como superior).

    Si alguna version no parsea (formato distinto a `X.Y`), logueja un
    warning y devuelve 0 (tratamiento conservador: marcar como no
    superior y disparar NARANJA aguas arriba).
    """
    if version_actual is None or not str(version_actual).strip():
        return -1

    cmp = VersionValidator.compare_versions(version_actual, version_nueva)
    if cmp is None:
        print(
            f"[upload_service] Aviso: no se pudo comparar versiones "
            f"{version_actual!r} vs {version_nueva!r}. Tratando como no superior."
        )
        return 0
    return cmp


def _validar_version(version: str) -> str:
    """Valida y normaliza una version `X.Y`. Lanza UploadError si invalida."""
    resultado = VersionValidator.validate_version(version)
    if not resultado["is_valid"]:
        raise UploadError(f"Version invalida: {resultado['message']}")
    return resultado["normalized"]


def _mover_archivo_a_proyecto(
    project_path: Path,
    archivo_origen: Path,
    codigo: str,
    version: str,
    estado: str,
) -> Path:
    """
    Mueve el archivo de origen a la carpeta correspondiente del proyecto.

    Convencion:
        02_Planos/<TIPO>/Working/<codigo>_v<version>_<estado>.<ext>
        TIPO segun extension: PDF / CAD (dwg, dxf) / RVT / Working (resto).

    Devuelve la ruta absoluta del archivo destino. Si el destino ya
    existe, se sobreescribe (caso de re-subida con misma version+estado).
    """
    if not archivo_origen.exists() or not archivo_origen.is_file():
        raise UploadError(f"Archivo origen no encontrado: {archivo_origen}")

    ext = archivo_origen.suffix.lower()
    subcarpeta = _EXT_A_SUBCARPETA.get(ext)

    planos_root = FolderResolver.resolve_planos(project_path)
    if subcarpeta is not None:
        destino_dir = planos_root / subcarpeta / "Working"
    else:
        destino_dir = planos_root / "Working"

    destino_dir.mkdir(parents=True, exist_ok=True)

    # Sanitizar codigo para nombre de archivo (espacios -> _, sin barras).
    codigo_safe = codigo.replace(" ", "_").replace("/", "_").replace("\\", "_")
    nombre_destino = f"{codigo_safe}_v{version}_{estado}{ext}"
    destino = destino_dir / nombre_destino

    # shutil.move funciona entre dispositivos y respeta atomicidad cuando
    # origen y destino estan en el mismo volumen. Si destino existe lo
    # sobreescribe.
    shutil.move(str(archivo_origen), str(destino))
    return destino


def _ruta_relativa(project_path: Path, ruta_absoluta: Path) -> str:
    """Ruta relativa al project_path para guardar en `archivos.ruta_archivo`."""
    try:
        return str(ruta_absoluta.relative_to(project_path))
    except ValueError:
        # Por si shutil.move devolvio una ruta fuera del proyecto.
        return str(ruta_absoluta)


def subir_plano_nuevo(
    project_path: Path,
    form_data: dict,
    archivo_path: Path,
) -> int:
    """
    Caso 1: crear un plano nuevo en el proyecto e insertar su primera version.

    Args:
        project_path: ruta de la carpeta del proyecto.
        form_data: dict con claves `codigo`, `nombre`, `version`, `autor`,
            `comentarios` (opcional).
        archivo_path: Path absoluta del archivo origen seleccionado por
            el usuario.

    Returns:
        plano_id recien creado.

    Raises:
        UploadError en validacion fallida, codigo duplicado o I/O.

    Atomicidad:
        El INSERT a planos + INSERT a archivos + cambiar_estado se
        ejecutan dentro de una transaccion. Si el move de archivo falla
        despues del commit, se intenta limpiar (raro: shutil.move se
        ejecuta DESPUES del commit; si falla, hay registro huerfano).
        Para evitar eso, movemos ANTES de insertar; si la insercion
        falla, deshacemos el move.
    """
    codigo = (form_data.get("codigo") or "").strip()
    nombre = (form_data.get("nombre") or codigo).strip()
    version = (form_data.get("version") or "").strip()
    autor = (form_data.get("autor") or "").strip() or None
    comentarios = (form_data.get("comentarios") or "").strip() or None

    if not codigo:
        raise UploadError("El codigo del plano es obligatorio.")
    if not version:
        raise UploadError("La version es obligatoria.")
    version_norm = _validar_version(version)

    project_path = Path(project_path)
    archivo_path = Path(archivo_path)
    db_manager = ensure_project_database(project_path)

    # Validar codigo unico antes de tocar nada.
    with db_manager.connection() as conn:
        exists = conn.execute(
            "SELECT 1 FROM planos WHERE codigo = ? LIMIT 1", (codigo,)
        ).fetchone()
        if exists is not None:
            raise UploadError(
                f"Ya existe un plano con codigo {codigo!r} en este proyecto."
            )

    # Mover archivo a su carpeta destino. El estado inicial sera S1
    # (primera subida pasa de GRIS a S1).
    destino_abs = _mover_archivo_a_proyecto(
        project_path, archivo_path, codigo, version_norm, "S1"
    )
    ruta_rel = _ruta_relativa(project_path, destino_abs)

    try:
        with db_manager.transaction() as conn:
            proyecto_row = conn.execute(
                "SELECT id FROM proyectos LIMIT 1"
            ).fetchone()
            if proyecto_row is None:
                raise UploadError("No existe fila en `proyectos` para este proyecto.")
            proyecto_id = proyecto_row["id"]

            orden_row = conn.execute(
                "SELECT COALESCE(MAX(orden), 0) + 1 AS o FROM planos "
                "WHERE proyecto_id = ?",
                (proyecto_id,),
            ).fetchone()
            next_orden = orden_row["o"]

            ext = archivo_path.suffix.lower().lstrip(".") or None

            cur = conn.execute(
                """
                INSERT INTO planos
                (proyecto_id, codigo, nombre, tipo_archivo, obligatorio,
                 orden, estado, version, autor)
                VALUES (?, ?, ?, ?, 0, ?, 'GRIS', ?, ?)
                """,
                (proyecto_id, codigo, nombre, ext, next_orden,
                 version_norm, autor),
            )
            plano_id = cur.lastrowid

            conn.execute(
                """
                INSERT INTO archivos
                (plano_id, version, autor, comentarios, ruta_archivo)
                VALUES (?, ?, ?, ?, ?)
                """,
                (plano_id, version_norm, autor, comentarios, ruta_rel),
            )

            # Estado inicial GRIS -> S1 (via cambiar_estado para que
            # quede registro en plano_estado_historial).
            cambiar_estado(conn, plano_id, "S1")

    except Exception:
        # Rollback de I/O: dejar el archivo en su sitio original no es
        # posible (shutil.move ya borro el origen). Lo dejamos en
        # destino para que el usuario lo recupere manualmente si quiere
        # y propagamos el error.
        raise

    return plano_id


def subir_nueva_version(
    project_path: Path,
    plano_id: int,
    form_data: dict,
    archivo_path: Path,
) -> dict:
    """
    Caso 2: subir una nueva version de un plano ya existente.

    Args:
        project_path: ruta de la carpeta del proyecto.
        plano_id: id de la fila en `planos`.
        form_data: dict con claves `version`, `autor`, `motivo_subida`
            (opcional).
        archivo_path: Path absoluta del archivo origen.

    Returns:
        dict con:
            - es_version_superior: bool
            - estado_nuevo: str (estado tras la operacion)
            - plano_id: int
            - ruta_archivo: str (relativa al proyecto)

    Raises:
        UploadError en validacion fallida o I/O.
    """
    version = (form_data.get("version") or "").strip()
    autor = (form_data.get("autor") or "").strip() or None
    motivo = (form_data.get("motivo_subida") or "").strip() or None

    if not version:
        raise UploadError("La version es obligatoria.")
    version_norm = _validar_version(version)

    project_path = Path(project_path)
    archivo_path = Path(archivo_path)
    db_manager = ensure_project_database(project_path)

    # Leer estado y version actuales del plano + numero de archivos
    # vinculados. "Primera subida" = no hay ningun archivo en la tabla
    # archivos para este plano. Basamos la deteccion en COUNT(archivos),
    # no solo en planos.version IS NULL, para evitar falsos positivos
    # si el campo denormalizado se queda atras por algun motivo.
    with db_manager.connection() as conn:
        row = conn.execute(
            "SELECT codigo, estado, version FROM planos WHERE id = ?",
            (plano_id,),
        ).fetchone()
        if row is None:
            raise UploadError(f"No existe plano con id={plano_id}.")
        codigo = row["codigo"]
        estado_actual = row["estado"]
        version_actual = row["version"]
        n_archivos = conn.execute(
            "SELECT COUNT(*) AS c FROM archivos WHERE plano_id = ?",
            (plano_id,),
        ).fetchone()["c"]

    cmp = comparar_versiones(version_actual, version_norm)
    es_version_superior = (cmp == -1)  # actual < nueva

    # Decidir estado nuevo:
    #   - primera_subida (no hay archivos vinculados) -> S1.
    #   - si es version superior y estado era ROJO -> S1 (rectificacion).
    #   - si NO es superior -> NARANJA (version incoherente).
    #   - resto -> estado se mantiene.
    primera_subida = n_archivos == 0
    if primera_subida:
        estado_nuevo = "S1"
    elif not es_version_superior:
        estado_nuevo = "NARANJA"
    elif estado_actual == "ROJO":
        estado_nuevo = "S1"
    else:
        estado_nuevo = estado_actual

    if estado_nuevo not in ESTADOS:
        # Defensiva: no deberia pasar, pero evitamos romper la BD.
        estado_nuevo = "GRIS"

    # Mover el archivo a destino. Usamos el estado_nuevo en el nombre
    # para que el filesystem refleje el estado tras la operacion.
    destino_abs = _mover_archivo_a_proyecto(
        project_path, archivo_path, codigo, version_norm, estado_nuevo
    )
    ruta_rel = _ruta_relativa(project_path, destino_abs)

    try:
        with db_manager.transaction() as conn:
            # INSERT del archivo siempre, sea version superior o no.
            conn.execute(
                """
                INSERT INTO archivos
                (plano_id, version, autor, comentarios, motivo_subida,
                 ruta_archivo)
                VALUES (?, ?, ?, NULL, ?, ?)
                """,
                (plano_id, version_norm, autor, motivo, ruta_rel),
            )

            # Si es superior, actualizar metadatos denormalizados del
            # plano (version, autor, tipo_archivo, fecha).
            if es_version_superior:
                ext = archivo_path.suffix.lower().lstrip(".") or None
                conn.execute(
                    """
                    UPDATE planos
                    SET version = ?,
                        autor = COALESCE(?, autor),
                        tipo_archivo = COALESCE(?, tipo_archivo),
                        fecha = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (version_norm, autor, ext, plano_id),
                )

            # Aplicar transicion de estado solo si cambia. cambiar_estado
            # ya es no-op cuando estado_actual == estado_nuevo, asi que
            # no duplica historial.
            cambiar_estado(conn, plano_id, estado_nuevo)

    except Exception:
        raise

    return {
        "es_version_superior": es_version_superior,
        "estado_nuevo": estado_nuevo,
        "plano_id": plano_id,
        "ruta_archivo": ruta_rel,
    }
