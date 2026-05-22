"""
Tests de integracion no interactivos per a la Fase 7 (subida masiva).

Escenaris coberts:
    [1] Bulk amb 3 arxius tots nous -> 3 OK; 3 noves files a planos+archivos.
    [2] Bulk mix: 1 plano nou + 1 versio superior d'existent + 1 versio
        inferior -> OK + OK + NARANJA.
    [3] Bulk amb un arxiu origen inexistent -> resta OK, l'erroni
        'error' i la BD no queda mig-inserida per aquell item.
    [4] Bulk amb dos items mateix codigo nou -> el primer crea el plano
        (OK), el segon es detectat com a versio i, com que la versio es
        identica, marca NARANJA (no superior).
    [5] Bulk amb item de form_data malformat (versio no parsejable) ->
        'error', resta no s'afecta.

Uso:
    cd repo
    PYTHONIOENCODING=utf-8 PYTHONUTF8=1 python scripts/test_fase7_bulk_upload.py

Crea PRJ-BULK_TEST temporal i el neteja al final.
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


PROJECT_CODE = "PRJ-BULK_TEST"


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")
    raise SystemExit(1)


def _ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def _setup_project() -> Path:
    folder = get_projects_root() / PROJECT_CODE
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)

    db = ensure_project_database(folder)
    with db.transaction() as conn:
        conn.execute(
            "UPDATE proyectos SET tipo='OBRA_NUEVA', nombre=?, lugar=?, "
            "descripcion=? WHERE codigo=?",
            ("Proyecto Fase 7", "Barcelona", "test_fase7_bulk_upload",
             PROJECT_CODE),
        )
        proyecto_id = conn.execute(
            "SELECT id FROM proyectos WHERE codigo = ?", (PROJECT_CODE,)
        ).fetchone()["id"]
        # Plano pre-existent per als casos de "nueva version" del test 2.
        conn.execute(
            """
            INSERT INTO planos
            (proyecto_id, codigo, nombre, obligatorio, orden, estado, version)
            VALUES (?, 'Existent_v2', 'Existent_v2', 0, 1, 'S2', '2.0')
            """,
            (proyecto_id,),
        )
    return folder


def _make_tmp(suffix: str = ".pdf") -> Path:
    f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    f.write(b"fake content")
    f.close()
    return Path(f.name)


def _count_planos(folder: Path) -> int:
    db = ensure_project_database(folder)
    with db.connection() as conn:
        return conn.execute("SELECT COUNT(*) AS c FROM planos").fetchone()["c"]


def _count_archivos_for(folder: Path, codigo: str) -> int:
    db = ensure_project_database(folder)
    with db.connection() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM archivos a "
            "JOIN planos p ON p.id = a.plano_id WHERE p.codigo = ?",
            (codigo,),
        ).fetchone()
        return row["c"]


def _get_plano(folder: Path, codigo: str) -> dict:
    db = ensure_project_database(folder)
    with db.connection() as conn:
        row = conn.execute(
            "SELECT estado, version, autor FROM planos WHERE codigo = ?",
            (codigo,),
        ).fetchone()
        return dict(row) if row else None


# ----- Escenaris ------------------------------------------------------


def test_1_todos_nuevos(folder: Path) -> None:
    print("[1] Bulk con 3 planos nuevos")
    from services.upload_service import subir_masivo

    items = []
    for codigo in ("Bulk_A", "Bulk_B", "Bulk_C"):
        items.append({
            "archivo_path": _make_tmp(".pdf"),
            "form_data": {
                "codigo": codigo, "nombre": codigo,
                "version": "1.0", "autor": "AB", "comentarios": "Primera",
            },
        })

    planos_pre = _count_planos(folder)
    results = subir_masivo(folder, items)

    if len(results) != 3:
        _fail(f"esperats 3 resultats, obtinguts {len(results)}")
    for r in results:
        if r["resultat"] != "ok":
            _fail(f"esperat 'ok', obtingut {r}")
    if _count_planos(folder) != planos_pre + 3:
        _fail("no s'han creat 3 planos")
    for codigo in ("Bulk_A", "Bulk_B", "Bulk_C"):
        p = _get_plano(folder, codigo)
        if p is None or p["estado"] != "S1":
            _fail(f"{codigo} estat esperat S1, obtingut {p}")
    _ok("3 nous OK; tots a estat S1")


def test_2_mix(folder: Path) -> None:
    print("[2] Bulk mix: 1 nou + 1 versio superior + 1 versio inferior")
    from services.upload_service import subir_masivo

    items = [
        # 1) Plano nou.
        {"archivo_path": _make_tmp(".pdf"),
         "form_data": {
             "codigo": "Bulk_Mix_Nou", "nombre": "Bulk_Mix_Nou",
             "version": "1.0", "autor": "CD", "comentarios": "nuevo",
         }},
        # 2) Versio superior sobre Existent_v2 (actual: 2.0, estat S2).
        {"archivo_path": _make_tmp(".pdf"),
         "form_data": {
             "codigo": "Existent_v2", "version": "3.0",
             "autor": "EF", "motivo_subida": "mejora",
         }},
        # 3) Versio inferior sobre Existent_v2 (post-test 2 estarà a 3.0).
        #    Pero subir_masivo processa items en ordre, llavors quan el
        #    tercer s'executa el segon ja ha pujat la 3.0. La versio 1.5
        #    es inferior a 3.0 -> NARANJA.
        {"archivo_path": _make_tmp(".pdf"),
         "form_data": {
             "codigo": "Existent_v2", "version": "1.5",
             "autor": "GH", "motivo_subida": "version vella",
         }},
    ]

    results = subir_masivo(folder, items)
    if len(results) != 3:
        _fail(f"esperats 3 resultats, obtinguts {len(results)}")
    if results[0]["resultat"] != "ok":
        _fail(f"item 1 (nou): esperat 'ok', obtingut {results[0]}")
    if results[1]["resultat"] != "ok":
        _fail(f"item 2 (superior): esperat 'ok', obtingut {results[1]}")
    if results[2]["resultat"] != "naranja":
        _fail(f"item 3 (inferior): esperat 'naranja', obtingut {results[2]}")

    p = _get_plano(folder, "Existent_v2")
    if p["version"] != "3.0":
        _fail(f"planos.version hauria de ser 3.0, es {p['version']!r}")
    if p["estado"] != "NARANJA":
        _fail(f"estat final esperat NARANJA, obtingut {p['estado']!r}")
    _ok("mix OK + OK + NARANJA; planos.version=3.0, estat NARANJA")


def test_3_archivo_inexistent(folder: Path) -> None:
    print("[3] Bulk amb un arxiu inexistent")
    from services.upload_service import subir_masivo

    ghost = Path(tempfile.gettempdir()) / "nope_does_not_exist_fase7.pdf"
    if ghost.exists():
        ghost.unlink()

    items = [
        {"archivo_path": _make_tmp(".pdf"),
         "form_data": {
             "codigo": "Bulk_Inex_OK_1", "nombre": "Bulk_Inex_OK_1",
             "version": "1.0", "autor": "AB", "comentarios": "ok",
         }},
        {"archivo_path": ghost,
         "form_data": {
             "codigo": "Bulk_Inex_ERROR", "nombre": "Bulk_Inex_ERROR",
             "version": "1.0", "autor": "AB", "comentarios": "x",
         }},
        {"archivo_path": _make_tmp(".pdf"),
         "form_data": {
             "codigo": "Bulk_Inex_OK_2", "nombre": "Bulk_Inex_OK_2",
             "version": "1.0", "autor": "AB", "comentarios": "ok",
         }},
    ]

    results = subir_masivo(folder, items)
    if [r["resultat"] for r in results] != ["ok", "error", "ok"]:
        _fail(f"esperat [ok, error, ok], obtingut {[r['resultat'] for r in results]}")
    if _get_plano(folder, "Bulk_Inex_ERROR") is not None:
        _fail("el plano amb arxiu inexistent NO hauria d'haver estat creat")
    if _get_plano(folder, "Bulk_Inex_OK_1") is None:
        _fail("el plano OK_1 hauria d'existir")
    if _get_plano(folder, "Bulk_Inex_OK_2") is None:
        _fail("el plano OK_2 hauria d'existir")
    _ok("error aïllat; planos OK no afectats")


def test_4_duplicat_mateix_bulk(folder: Path) -> None:
    print("[4] Bulk amb 2 items mateix codigo nou (mateixa versio)")
    from services.upload_service import subir_masivo

    items = [
        {"archivo_path": _make_tmp(".pdf"),
         "form_data": {
             "codigo": "Bulk_Dup", "nombre": "Bulk_Dup",
             "version": "1.0", "autor": "AB", "comentarios": "primer",
         }},
        # Segon: el cache ja te 'Bulk_Dup', llavors es detecta com a
        # "nueva version" amb v1.0. comparar_versiones("1.0","1.0")=0
        # -> no superior -> NARANJA.
        {"archivo_path": _make_tmp(".pdf"),
         "form_data": {
             "codigo": "Bulk_Dup", "version": "1.0",
             "autor": "CD", "motivo_subida": "duplicat",
         }},
    ]

    results = subir_masivo(folder, items)
    if results[0]["resultat"] != "ok":
        _fail(f"item 1 (crea plano): esperat 'ok', obtingut {results[0]}")
    if results[1]["resultat"] != "naranja":
        _fail(f"item 2 (mateixa versio): esperat 'naranja', obtingut {results[1]}")
    p = _get_plano(folder, "Bulk_Dup")
    if p["estado"] != "NARANJA":
        _fail(f"estat esperat NARANJA, obtingut {p['estado']!r}")
    if _count_archivos_for(folder, "Bulk_Dup") != 2:
        _fail("haurien d'haver-hi 2 archivos vinculats")
    _ok("primer crea (S1->NARANJA al duplicat); 2 archivos al historic")


def test_5_form_data_malformat(folder: Path) -> None:
    print("[5] Bulk amb form_data malformat (versio no parsejable)")
    from services.upload_service import subir_masivo

    items = [
        {"archivo_path": _make_tmp(".pdf"),
         "form_data": {
             "codigo": "Bulk_Bad_1", "nombre": "Bulk_Bad_1",
             "version": "abc", "autor": "AB", "comentarios": "x",
         }},
        {"archivo_path": _make_tmp(".pdf"),
         "form_data": {
             "codigo": "Bulk_Bad_2_OK", "nombre": "Bulk_Bad_2_OK",
             "version": "1.0", "autor": "AB", "comentarios": "ok",
         }},
    ]
    results = subir_masivo(folder, items)
    if results[0]["resultat"] != "error":
        _fail(f"item 1 (version invalida): esperat 'error', obtingut {results[0]}")
    if results[1]["resultat"] != "ok":
        _fail(f"item 2 (correcte): esperat 'ok', obtingut {results[1]}")
    if _get_plano(folder, "Bulk_Bad_1") is not None:
        _fail("plano amb version invalida NO hauria de crear-se")
    if _get_plano(folder, "Bulk_Bad_2_OK") is None:
        _fail("plano OK hauria d'existir")
    _ok("error aïllat per format de versio invalid")


def main() -> int:
    print("== Tests Fase 7 ==")
    folder = _setup_project()
    try:
        test_1_todos_nuevos(folder)
        test_2_mix(folder)
        test_3_archivo_inexistent(folder)
        test_4_duplicat_mateix_bulk(folder)
        test_5_form_data_malformat(folder)
        print()
        print("[ALL PASSED]")
    finally:
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
