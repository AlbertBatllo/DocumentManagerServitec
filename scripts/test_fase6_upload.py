"""
Tests de integracion no interactivos para la Fase 6 (subida individual).

Escenarios cubiertos:
    [1] subir_plano_nuevo: codigo unico -> planos+archivos+historial OK,
        estado S1, archivo movido a 02_Planos/<TIPO>/Working.
    [2] subir_plano_nuevo: codigo duplicado -> UploadError, cap fila
        inserida.
    [3] subir_nueva_version: version superior (2.0 sobre 1.0) -> UPDATE
        planos, INSERT archivos con motivo_subida, estado se mantiene.
    [4] subir_nueva_version: version superior pero estado actual ROJO
        -> pasa a S1 + historial.
    [5] subir_nueva_version: version inferior (1.0 sobre 2.0) ->
        INSERT archivos, estado pasa a NARANJA + historial.
    [6] subir_nueva_version: archivo origen inexistente -> UploadError,
        cap fila inserida (rollback total).

Uso:
    cd repo
    PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/test_fase6_upload.py

El test crea su propio proyecto temporal `PRJ-UPLOAD_TEST` al lado de
los demas. Lo borra al final para que el suite sea reproducible.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))


from utils.app_paths import get_projects_root  # noqa: E402
from utils.database.project_database_manager import (  # noqa: E402
    ensure_project_database,
)


PROJECT_CODE = "PRJ-UPLOAD_TEST"


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")
    raise SystemExit(1)


def _ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def _setup_project() -> Path:
    """Crea el proyecto temporal con un plano pre-existente."""
    folder = get_projects_root() / PROJECT_CODE
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)

    db = ensure_project_database(folder)
    with db.transaction() as conn:
        conn.execute(
            "UPDATE proyectos SET tipo='REFORMA', nombre=?, lugar=?, descripcion=? "
            "WHERE codigo=?",
            ("Proyecto Fase 6", "Barcelona", "Generado por test_fase6_upload.py",
             PROJECT_CODE),
        )
        proyecto_id = conn.execute(
            "SELECT id FROM proyectos WHERE codigo = ?", (PROJECT_CODE,)
        ).fetchone()["id"]
        # Plano pre-existente "Plano_Existent" en estado GRIS sin
        # version. Usado en los escenarios 3-6.
        conn.execute(
            """
            INSERT INTO planos
            (proyecto_id, codigo, nombre, obligatorio, orden, estado)
            VALUES (?, 'Plano_Existent', 'Plano_Existent', 0, 1, 'GRIS')
            """,
            (proyecto_id,),
        )
    return folder


def _make_temp_file(suffix: str = ".pdf", content: bytes = b"fake content") -> Path:
    """Crea un archivo temporal con contenido fake. Devuelve su Path."""
    f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


def _get_plano(folder: Path, codigo: str) -> dict:
    db = ensure_project_database(folder)
    with db.connection() as conn:
        row = conn.execute(
            "SELECT id, codigo, nombre, estado, version, autor, tipo_archivo "
            "FROM planos WHERE codigo = ?", (codigo,)
        ).fetchone()
        return dict(row) if row else None


def _count_archivos(folder: Path, plano_id: int) -> int:
    db = ensure_project_database(folder)
    with db.connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM archivos WHERE plano_id = ?", (plano_id,)
        ).fetchone()
        return row["c"]


def _last_historial(folder: Path, plano_id: int) -> dict:
    db = ensure_project_database(folder)
    with db.connection() as conn:
        row = conn.execute(
            "SELECT estado_anterior, estado_nuevo FROM plano_estado_historial "
            "WHERE plano_id = ? ORDER BY id DESC LIMIT 1", (plano_id,)
        ).fetchone()
        return dict(row) if row else None


# ----- Escenarios ------------------------------------------------------


def test_1_subir_plano_nuevo_ok(folder: Path) -> int:
    print("[1] subir_plano_nuevo: codigo unico")
    from services.upload_service import subir_plano_nuevo

    archivo = _make_temp_file(".pdf")
    plano_id = subir_plano_nuevo(
        folder,
        {"codigo": "Plano_Nuevo_T1", "nombre": "Plano Nuevo Test 1",
         "version": "1.0", "autor": "AB", "comentarios": "Primera version"},
        archivo,
    )
    p = _get_plano(folder, "Plano_Nuevo_T1")
    if p is None:
        _fail("plano no insertado")
    if p["estado"] != "S1":
        _fail(f"estado esperado S1, obtenido {p['estado']!r}")
    if p["version"] != "1.0":
        _fail(f"version esperada 1.0, obtenida {p['version']!r}")
    if _count_archivos(folder, plano_id) != 1:
        _fail("archivos no inserido")
    hist = _last_historial(folder, plano_id)
    if hist is None or hist["estado_anterior"] != "GRIS" or hist["estado_nuevo"] != "S1":
        _fail(f"historial incorrecto: {hist}")
    # Verificar archivo fisico.
    db = ensure_project_database(folder)
    with db.connection() as conn:
        row = conn.execute(
            "SELECT ruta_archivo FROM archivos WHERE plano_id = ?", (plano_id,)
        ).fetchone()
    ruta_abs = folder / row["ruta_archivo"]
    if not ruta_abs.exists():
        _fail(f"archivo fisico no encontrado: {ruta_abs}")
    _ok(f"plano_id={plano_id}, estado=S1, archivo en {row['ruta_archivo']}")
    return plano_id


def test_2_subir_plano_nuevo_duplicado(folder: Path) -> None:
    print("[2] subir_plano_nuevo: codigo duplicado")
    from services.upload_service import subir_plano_nuevo, UploadError

    archivo = _make_temp_file(".pdf")
    # Conteo previo de filas en planos.
    db = ensure_project_database(folder)
    with db.connection() as conn:
        antes = conn.execute("SELECT COUNT(*) AS c FROM planos").fetchone()["c"]

    try:
        subir_plano_nuevo(
            folder,
            {"codigo": "Plano_Nuevo_T1", "nombre": "Dup",
             "version": "1.0", "autor": "AB"},
            archivo,
        )
    except UploadError:
        pass
    else:
        _fail("no se lanzo UploadError para codigo duplicado")

    with db.connection() as conn:
        despues = conn.execute("SELECT COUNT(*) AS c FROM planos").fetchone()["c"]
    if despues != antes:
        _fail(f"se inserto fila inesperada: antes={antes}, despues={despues}")
    # El archivo temporal sigue donde lo creamos: la validacion de
    # duplicado se hace ANTES del move.
    if not archivo.exists():
        _fail("archivo temporal eliminado por error en validacion duplicado")
    archivo.unlink()
    _ok("UploadError lanzado, BD sin cambios")


def test_3_version_superior(folder: Path) -> int:
    print("[3] subir_nueva_version: version superior (primera subida sobre plano GRIS)")
    from services.upload_service import subir_nueva_version

    plano = _get_plano(folder, "Plano_Existent")
    plano_id = plano["id"]
    archivo = _make_temp_file(".pdf")
    result = subir_nueva_version(
        folder, plano_id,
        {"version": "1.0", "autor": "CD", "motivo_subida": "Subida inicial"},
        archivo,
    )
    if not result["es_version_superior"]:
        _fail(f"esperado es_version_superior=True (primera subida), obtenido {result}")
    if result["estado_nuevo"] != "S1":
        _fail(f"esperado estado S1, obtenido {result['estado_nuevo']!r}")
    p2 = _get_plano(folder, "Plano_Existent")
    if p2["version"] != "1.0":
        _fail(f"version no actualizada: {p2['version']!r}")
    if _count_archivos(folder, plano_id) != 1:
        _fail("archivo no insertado en 'archivos'")
    hist = _last_historial(folder, plano_id)
    if hist["estado_anterior"] != "GRIS" or hist["estado_nuevo"] != "S1":
        _fail(f"historial primera subida incorrecto: {hist}")
    _ok("primera subida GRIS->S1, version=1.0")

    # Ahora subir version superior 2.0 con estado actual S1: estado
    # debe MANTENERSE (no es ROJO, no es no-superior).
    archivo2 = _make_temp_file(".pdf", b"v2")
    result2 = subir_nueva_version(
        folder, plano_id,
        {"version": "2.0", "autor": "EF", "motivo_subida": "Mejora"},
        archivo2,
    )
    if not result2["es_version_superior"]:
        _fail(f"esperado superior, obtenido {result2}")
    if result2["estado_nuevo"] != "S1":
        _fail(f"estado deberia mantenerse en S1, obtenido {result2['estado_nuevo']!r}")
    p3 = _get_plano(folder, "Plano_Existent")
    if p3["version"] != "2.0":
        _fail(f"version no actualizada a 2.0: {p3['version']!r}")
    if _count_archivos(folder, plano_id) != 2:
        _fail(f"deberian haber 2 archivos, hay {_count_archivos(folder, plano_id)}")
    _ok("version superior S1 estado mantiene; planos.version=2.0; 2 archivos")
    return plano_id


def test_4_superior_desde_rojo(folder: Path, plano_id: int) -> None:
    print("[4] subir_nueva_version: superior con estado actual ROJO -> S1")
    from services.upload_service import subir_nueva_version
    from utils.estados import cambiar_estado

    # Forzar estado ROJO manualmente para simular un rechazo previo.
    db = ensure_project_database(folder)
    with db.transaction() as conn:
        cambiar_estado(conn, plano_id, "ROJO")
    p = _get_plano(folder, "Plano_Existent")
    if p["estado"] != "ROJO":
        _fail(f"no se pudo forzar ROJO: {p['estado']!r}")

    archivo = _make_temp_file(".pdf", b"v3")
    result = subir_nueva_version(
        folder, plano_id,
        {"version": "3.0", "autor": "GH", "motivo_subida": "Correccion"},
        archivo,
    )
    if result["estado_nuevo"] != "S1":
        _fail(f"esperado S1, obtenido {result['estado_nuevo']!r}")
    hist = _last_historial(folder, plano_id)
    if hist["estado_anterior"] != "ROJO" or hist["estado_nuevo"] != "S1":
        _fail(f"historial ROJO->S1 incorrecto: {hist}")
    _ok("estado ROJO->S1 con archivo v3.0")


def test_5_no_superior_naranja(folder: Path, plano_id: int) -> None:
    print("[5] subir_nueva_version: inferior -> NARANJA")
    from services.upload_service import subir_nueva_version

    # planos.version actual = 3.0 (post test 4). Subimos 2.5 -> inferior.
    archivo = _make_temp_file(".pdf", b"v2.5")
    result = subir_nueva_version(
        folder, plano_id,
        {"version": "2.5", "autor": "IJ", "motivo_subida": "Equivocado a proposito"},
        archivo,
    )
    if result["es_version_superior"]:
        _fail(f"esperado no superior, obtenido {result}")
    if result["estado_nuevo"] != "NARANJA":
        _fail(f"esperado NARANJA, obtenido {result['estado_nuevo']!r}")
    p = _get_plano(folder, "Plano_Existent")
    # planos.version NO debe haberse actualizado (no es superior).
    if p["version"] != "3.0":
        _fail(f"version no deberia haberse actualizado: {p['version']!r}")
    hist = _last_historial(folder, plano_id)
    if hist["estado_anterior"] != "S1" or hist["estado_nuevo"] != "NARANJA":
        _fail(f"historial S1->NARANJA incorrecto: {hist}")
    _ok("inferior 2.5 con planos.version=3.0; estado NARANJA")


def test_6_archivo_inexistente(folder: Path, plano_id: int) -> None:
    print("[6] subir_nueva_version: archivo origen inexistente -> rollback")
    from services.upload_service import subir_nueva_version, UploadError

    archivos_antes = _count_archivos(folder, plano_id)
    p_antes = _get_plano(folder, "Plano_Existent")

    fake_path = Path(tempfile.gettempdir()) / "definitely_does_not_exist_fase6.pdf"
    if fake_path.exists():
        fake_path.unlink()

    try:
        subir_nueva_version(
            folder, plano_id,
            {"version": "4.0", "autor": "KL", "motivo_subida": "Nope"},
            fake_path,
        )
    except UploadError:
        pass
    else:
        _fail("no se lanzo UploadError para archivo inexistente")

    archivos_despues = _count_archivos(folder, plano_id)
    p_despues = _get_plano(folder, "Plano_Existent")

    if archivos_despues != archivos_antes:
        _fail(f"se inserto archivo fantasma: antes={archivos_antes}, despues={archivos_despues}")
    if p_despues["estado"] != p_antes["estado"]:
        _fail(f"estado cambio sin debido: {p_antes['estado']} -> {p_despues['estado']}")
    if p_despues["version"] != p_antes["version"]:
        _fail(f"version cambio sin debido: {p_antes['version']} -> {p_despues['version']}")
    _ok("rollback OK: BD intacta")


def main() -> int:
    print("== Tests Fase 6 ==")
    folder = _setup_project()
    try:
        test_1_subir_plano_nuevo_ok(folder)
        test_2_subir_plano_nuevo_duplicado(folder)
        plano_id = test_3_version_superior(folder)
        test_4_superior_desde_rojo(folder, plano_id)
        test_5_no_superior_naranja(folder, plano_id)
        test_6_archivo_inexistente(folder, plano_id)
        print()
        print("[ALL PASSED]")
    finally:
        # Limpiar para no dejar la carpeta colgando.
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
