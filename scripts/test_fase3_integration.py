"""
Tests de integracion no interactivos para la Fase 3.

Verifica:
    - Los modulos nuevos se importan sin errores.
    - `load_project_for_edit` lee correctamente la estructura del
      proyecto seed.
    - `check_delete_safety` distingue las tres ramas (safe / no_history
      / has_history) usando los planos del seed.
    - `editar_proyecto` aplica un batch completo (rename de plano, add
      detalle nuevo, revertir estado) y los cambios persisten.

No abre Tkinter ni el dialogo. Para validar el dialogo y el boton del
dashboard, usar el seed + ejecutar la app manualmente.

Uso:
    cd repo
    python scripts/test_fase3_integration.py
"""

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))


from utils.app_paths import get_projects_root  # noqa: E402
from utils.database.project_database_manager import (  # noqa: E402
    ensure_project_database,
)


PROJECT_CODE = "PRJ-EDIT_TEST"


def _fail(msg: str) -> None:
    print(f"  [FAIL] {msg}")
    raise SystemExit(1)


def _ok(msg: str) -> None:
    print(f"  [OK]   {msg}")


def test_imports() -> None:
    print("[1] Imports de los modulos nuevos / modificados")
    import services.project_edit_service  # noqa: F401
    import views.project_form_view  # noqa: F401
    import views.plano_delete_dialog  # noqa: F401
    _ok("services.project_edit_service")
    _ok("views.project_form_view")
    _ok("views.plano_delete_dialog")

    # Sanity: las funciones publicas esperadas existen.
    from services.project_edit_service import (
        load_project_for_edit, check_delete_safety, editar_proyecto,
        ProjectEditError,
    )
    assert callable(load_project_for_edit)
    assert callable(check_delete_safety)
    assert callable(editar_proyecto)
    assert issubclass(ProjectEditError, Exception)
    _ok("Funciones esperadas del servicio presentes")

    from views.project_form_view import ProjectFormView
    assert hasattr(ProjectFormView, "show_create")
    assert hasattr(ProjectFormView, "show_edit")
    _ok("ProjectFormView.show_create y show_edit existen")

    from views.plano_delete_dialog import ask_delete_action
    assert callable(ask_delete_action)
    _ok("plano_delete_dialog.ask_delete_action existe")


def test_load_project_for_edit() -> dict:
    print("[2] load_project_for_edit lee la estructura del seed")
    from services.project_edit_service import load_project_for_edit

    folder = get_projects_root() / PROJECT_CODE
    if not folder.exists():
        _fail(f"Carpeta {folder} no existe. Ejecuta seed_edit_test_project.py.")

    data = load_project_for_edit(folder)

    if data.get("codigo") != PROJECT_CODE:
        _fail(f"codigo esperado {PROJECT_CODE!r}, obtenido {data.get('codigo')!r}")
    if data.get("tipo") != "REFORMA":
        _fail(f"tipo esperado 'REFORMA', obtenido {data.get('tipo')!r}")
    if not data.get("nombre"):
        _fail("nombre esta vacio")

    planos = data.get("planos", [])
    if len(planos) != 6:
        _fail(f"esperados 6 planos (3 oblig + 3 det), encontrados {len(planos)}")
    obligs = [p for p in planos if p["obligatorio"]]
    detalles = [p for p in planos if not p["obligatorio"]]
    if len(obligs) != 3 or len(detalles) != 3:
        _fail(
            f"reparto esperado 3 oblig + 3 detalles, obtenido "
            f"{len(obligs)} + {len(detalles)}"
        )
    nombres_det = {p["nombre"] for p in detalles}
    expected_det = {"Detalle_Con_Historial", "Detalle_Solo_Archivos", "Detalle_Multi_Archivo"}
    if nombres_det != expected_det:
        _fail(f"detalles inesperados: {nombres_det}")

    _ok(f"6 planos cargados ({len(obligs)} obligatorios + {len(detalles)} detalles)")
    return data


def test_check_delete_safety(data: dict) -> None:
    print("[3] check_delete_safety distingue las tres ramas")
    from services.project_edit_service import check_delete_safety

    folder = get_projects_root() / PROJECT_CODE
    planos_by_name = {p["nombre"]: p for p in data["planos"]}

    # Un obligatorio cualquiera -> safe.
    obligs = [p for p in data["planos"] if p["obligatorio"]]
    safe_pid = obligs[0]["id"]
    sev = check_delete_safety(folder, safe_pid)
    if sev != "safe":
        _fail(f"esperado 'safe' para obligatorio, obtenido {sev!r}")
    _ok(f"obligatorio id={safe_pid} -> safe")

    no_hist_pid = planos_by_name["Detalle_Solo_Archivos"]["id"]
    sev = check_delete_safety(folder, no_hist_pid)
    if sev != "no_history":
        _fail(f"esperado 'no_history' para Detalle_Solo_Archivos, obtenido {sev!r}")
    _ok(f"Detalle_Solo_Archivos id={no_hist_pid} -> no_history")

    hist_pid = planos_by_name["Detalle_Con_Historial"]["id"]
    sev = check_delete_safety(folder, hist_pid)
    if sev != "has_history":
        _fail(f"esperado 'has_history' para Detalle_Con_Historial, obtenido {sev!r}")
    _ok(f"Detalle_Con_Historial id={hist_pid} -> has_history")


def test_editar_proyecto_batch(data: dict) -> None:
    print("[4] editar_proyecto aplica un batch completo y persiste")
    from services.project_edit_service import (
        editar_proyecto, load_project_for_edit,
    )

    folder = get_projects_root() / PROJECT_CODE
    planos_by_name = {p["nombre"]: p for p in data["planos"]}

    # Estado de partida: Detalle_Con_Historial esta en S1.
    hist_pid = planos_by_name["Detalle_Con_Historial"]["id"]
    # El obligatorio que vamos a renombrar.
    target_emp = planos_by_name["Emplazamiento"]
    # Mantener al resto sin cambios.

    # Construir el batch como lo entregaria el view:
    form_data = {
        "tipo": "REFORMA",
        "nombre": "Proyecto Fase 3 - editado",
        "lugar": "Tarragona",
        "descripcion": "Modificado por test_fase3_integration.py",
        "planos_existentes": [
            # rename del primer obligatorio.
            {
                "id": target_emp["id"],
                "nombre": "Emplazamiento_v2",
                "codigo": "Emplazamiento_v2",
            },
            # Mantener el resto sin cambios visibles.
            *[
                {"id": p["id"], "nombre": p["nombre"], "codigo": p["codigo"]}
                for p in data["planos"]
                if p["id"] != target_emp["id"]
            ],
        ],
        "planos_nuevos_detalle": ["Detalle_Nuevo_Test"],
        "planos_a_borrar": [],
        "planos_a_revertir": [hist_pid],  # S1 -> BLANCO esperado.
    }

    editar_proyecto(folder, form_data)
    _ok("editar_proyecto ejecutado sin excepcion")

    # Releer.
    data2 = load_project_for_edit(folder)
    if data2["nombre"] != "Proyecto Fase 3 - editado":
        _fail(f"nombre no actualizado: {data2['nombre']!r}")
    if data2["lugar"] != "Tarragona":
        _fail(f"lugar no actualizado: {data2['lugar']!r}")
    _ok("nombre y lugar actualizados")

    planos2 = {p["nombre"]: p for p in data2["planos"]}
    if "Emplazamiento_v2" not in planos2:
        _fail("rename de Emplazamiento -> Emplazamiento_v2 no aplicado")
    if "Emplazamiento" in planos2:
        _fail("la fila Emplazamiento original sigue existiendo")
    _ok("rename de plano aplicado")

    if "Detalle_Nuevo_Test" not in planos2:
        _fail("detalle nuevo no insertado")
    if planos2["Detalle_Nuevo_Test"]["estado"] != "GRIS":
        _fail(
            f"detalle nuevo deberia estar en GRIS, esta en "
            f"{planos2['Detalle_Nuevo_Test']['estado']!r}"
        )
    _ok("detalle nuevo insertado en estado GRIS")

    revertido = planos2["Detalle_Con_Historial"]
    if revertido["estado"] != "BLANCO":
        _fail(
            f"revert de S1 -> BLANCO no aplicado; estado actual "
            f"{revertido['estado']!r}"
        )
    _ok("revert de estado aplicado (S1 -> BLANCO)")

    # Comprobar que se registro una nueva fila en plano_estado_historial.
    db = ensure_project_database(folder)
    with db.connection() as conn:
        row = conn.execute(
            "SELECT estado_anterior, estado_nuevo FROM plano_estado_historial "
            "WHERE plano_id = ? ORDER BY id DESC LIMIT 1",
            (hist_pid,),
        ).fetchone()
    if row is None:
        _fail("no se encontro la fila de historial del revert")
    if row["estado_anterior"] != "S1" or row["estado_nuevo"] != "BLANCO":
        _fail(
            f"historial revert incorrecto: anterior={row['estado_anterior']!r}, "
            f"nuevo={row['estado_nuevo']!r}"
        )
    _ok("revert registrado en plano_estado_historial")


def test_delete_with_history() -> None:
    print("[5] Borrado de plano con historial elimina archivos + historial")
    from services.project_edit_service import (
        editar_proyecto, load_project_for_edit,
    )

    folder = get_projects_root() / PROJECT_CODE
    data = load_project_for_edit(folder)
    planos_by_name = {p["nombre"]: p for p in data["planos"]}

    if "Detalle_Con_Historial" not in planos_by_name:
        _fail("Detalle_Con_Historial no encontrado (test 4 puede haber fallado)")
    target = planos_by_name["Detalle_Con_Historial"]
    target_id = target["id"]

    db = ensure_project_database(folder)
    with db.connection() as conn:
        archivos_pre = conn.execute(
            "SELECT COUNT(*) AS c FROM archivos WHERE plano_id = ?",
            (target_id,),
        ).fetchone()["c"]
        hist_pre = conn.execute(
            "SELECT COUNT(*) AS c FROM plano_estado_historial WHERE plano_id = ?",
            (target_id,),
        ).fetchone()["c"]
    if archivos_pre == 0 or hist_pre == 0:
        _fail(
            f"el plano deberia tener archivos e historial antes de borrar; "
            f"archivos={archivos_pre}, hist={hist_pre}"
        )

    form_data = {
        "tipo": data["tipo"],
        "nombre": data["nombre"],
        "lugar": data["lugar"],
        "descripcion": data["descripcion"],
        "planos_existentes": [
            {"id": p["id"], "nombre": p["nombre"], "codigo": p["codigo"]}
            for p in data["planos"]
            if p["id"] != target_id
        ],
        "planos_nuevos_detalle": [],
        "planos_a_borrar": [target_id],
        "planos_a_revertir": [],
    }
    editar_proyecto(folder, form_data)

    with db.connection() as conn:
        plano_row = conn.execute(
            "SELECT COUNT(*) AS c FROM planos WHERE id = ?", (target_id,)
        ).fetchone()["c"]
        archivos_post = conn.execute(
            "SELECT COUNT(*) AS c FROM archivos WHERE plano_id = ?",
            (target_id,),
        ).fetchone()["c"]
        hist_post = conn.execute(
            "SELECT COUNT(*) AS c FROM plano_estado_historial WHERE plano_id = ?",
            (target_id,),
        ).fetchone()["c"]
    if plano_row != 0:
        _fail("la fila del plano no fue eliminada")
    if archivos_post != 0:
        _fail(f"archivos asociados no cascadearon: {archivos_post} restantes")
    if hist_post != 0:
        _fail(f"historial asociado no cascadeo: {hist_post} restantes")
    _ok("CASCADE de archivos e historial OK al borrar plano")


def main() -> int:
    print("== Tests Fase 3 ==")
    test_imports()
    data = test_load_project_for_edit()
    test_check_delete_safety(data)
    test_editar_proyecto_batch(data)
    test_delete_with_history()
    print()
    print("[ALL PASSED]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
