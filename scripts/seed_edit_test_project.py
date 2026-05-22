"""
Genera un proyecto de prueba 'PRJ-EDIT_TEST' para validar manualmente la
Fase 3 (edicion de proyecto).

Crea:
    - Carpeta del proyecto al lado de los demas PRJ-* (mismo root que
      usa la app: `get_projects_root()`).
    - BD inicializada con la migracion Fase 1 aplicada.
    - Fila en `proyectos` con tipo, nombre, lugar, descripcion poblados.
    - 3 planos obligatorios + 3 detalles.
    - Para uno de los detalles ("Detalle_Con_Historial"):
        * 2 filas en `archivos` simulando subidas anteriores.
        * 2 filas en `plano_estado_historial` (GRIS -> BLANCO -> S1).
        * Estado actual del plano = 'S1'.
      Esto activa la rama "has_history" del dialogo de borrado.
    - Para otro detalle ("Detalle_Solo_Archivos"):
        * 1 fila en `archivos`, sin historial de estados.
      Esto activa la rama "no_history" del dialogo.
    - Para el tercer detalle ("Detalle_Multi_Archivo"):
        * 3 filas en `archivos` (v1.0, v1.1, v2.0) para validar
          visualmente la columna Version con la mas reciente y el
          historial via Ver Historial.
        * Estado actual del plano = 'S2' (verde) para cubrir un color
          distinto al S1 (amarillo) de Detalle_Con_Historial.
      El test 5 de test_fase3_integration.py NO toca este plano, asi
      que sobrevive a la batería y queda disponible para validacion
      visual permanente en el dashboard.

Uso:
    cd repo
    python scripts/seed_edit_test_project.py

El script es idempotente: si la carpeta ya existe, lo dice y no toca
nada. Borra la carpeta a mano si quieres regenerarla limpia.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path


# Aniadir repo/src al sys.path para poder importar utils.* sin instalar.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))


from utils.app_paths import get_projects_root  # noqa: E402
from utils.database.project_database_manager import (  # noqa: E402
    ensure_project_database,
)


PROJECT_CODE = "PRJ-EDIT_TEST"


def main() -> int:
    root = get_projects_root()
    folder = root / PROJECT_CODE
    if folder.exists():
        print(f"[SKIP] La carpeta {folder} ya existe. Borrala a mano "
              "si quieres regenerarla.")
        return 0

    print(f"[1/4] Creando carpeta {folder}")
    folder.mkdir(parents=True, exist_ok=False)

    print(f"[2/4] Inicializando BD y aplicando migracion Fase 1")
    db = ensure_project_database(folder)

    print(f"[3/4] Poblando proyecto + planos + archivos + historial")
    descripcion_test = (
        "Generado por seed_edit_test_project.py para validar el flujo "
        "de edicion de proyectos."
    )
    with db.transaction() as conn:
        # Actualizar la fila auto-creada por la migracion.
        conn.execute(
            """
            UPDATE proyectos
            SET tipo = 'REFORMA',
                nombre = ?,
                lugar = ?,
                descripcion = ?,
                modificado_en = CURRENT_TIMESTAMP
            WHERE codigo = ?
            """,
            (
                "Proyecto de prueba para Fase 3",
                "Barcelona",
                descripcion_test,
                PROJECT_CODE,
            ),
        )
        proyecto_id = conn.execute(
            "SELECT id FROM proyectos WHERE codigo = ?", (PROJECT_CODE,)
        ).fetchone()["id"]

        # 3 obligatorios.
        obligatorios = ["Emplazamiento", "Planta_General", "Estructura"]
        for orden, nombre in enumerate(obligatorios, start=1):
            conn.execute(
                """
                INSERT INTO planos
                (proyecto_id, codigo, nombre, obligatorio, orden, estado)
                VALUES (?, ?, ?, 1, ?, 'GRIS')
                """,
                (proyecto_id, nombre, nombre, orden),
            )

        # 3 detalles: uno con historial y archivos, otro solo con
        # archivos, y un tercero con multiples archivos en estado S2
        # (verde) para validar visualmente otro color del modelo Fase 5.
        detalles = [
            ("Detalle_Con_Historial", "S1"),     # has_history
            ("Detalle_Solo_Archivos", "GRIS"),   # no_history
            ("Detalle_Multi_Archivo", "S2"),     # validacion visual S2
        ]
        detalle_ids = {}
        for offset, (nombre, estado_final) in enumerate(detalles):
            orden = len(obligatorios) + 1 + offset
            cur = conn.execute(
                """
                INSERT INTO planos
                (proyecto_id, codigo, nombre, obligatorio, orden, estado)
                VALUES (?, ?, ?, 0, ?, ?)
                """,
                (proyecto_id, nombre, nombre, orden, estado_final),
            )
            detalle_ids[nombre] = cur.lastrowid

        # Historial de estados solo para "Detalle_Con_Historial":
        #   GRIS -> BLANCO (hace 2 dias), BLANCO -> S1 (hace 1 dia).
        plano_id_hist = detalle_ids["Detalle_Con_Historial"]
        dos_dias = (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d %H:%M:%S")
        un_dia = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            """
            INSERT INTO plano_estado_historial
            (plano_id, estado_anterior, estado_nuevo, cambiado_en)
            VALUES (?, 'GRIS', 'BLANCO', ?)
            """,
            (plano_id_hist, dos_dias),
        )
        conn.execute(
            """
            INSERT INTO plano_estado_historial
            (plano_id, estado_anterior, estado_nuevo, cambiado_en)
            VALUES (?, 'BLANCO', 'S1', ?)
            """,
            (plano_id_hist, un_dia),
        )

        # Archivos asociados para ambos detalles.
        conn.execute(
            """
            INSERT INTO archivos
            (plano_id, version, autor, fecha, comentarios, ruta_archivo)
            VALUES (?, '1.0', 'AB', ?, 'Primera subida', ?)
            """,
            (plano_id_hist, dos_dias, "Detalle_Con_Historial_v1.0_BLANCO.pdf"),
        )
        conn.execute(
            """
            INSERT INTO archivos
            (plano_id, version, autor, fecha, comentarios, ruta_archivo)
            VALUES (?, '1.1', 'AB', ?, 'Revision tecnica', ?)
            """,
            (plano_id_hist, un_dia, "Detalle_Con_Historial_v1.1_S1.pdf"),
        )
        conn.execute(
            """
            INSERT INTO archivos
            (plano_id, version, autor, fecha, comentarios, ruta_archivo)
            VALUES (?, '1.0', 'CD', CURRENT_TIMESTAMP, 'Sin historial estados', ?)
            """,
            (detalle_ids["Detalle_Solo_Archivos"], "Detalle_Solo_Archivos_v1.0.pdf"),
        )

        # Detalle_Multi_Archivo: 3 versiones para validar Treeview con
        # mas de un archivo (el dashboard muestra el mas reciente).
        plano_id_multi = detalle_ids["Detalle_Multi_Archivo"]
        tres_dias = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        dia_y_medio = (datetime.now() - timedelta(hours=36)).strftime("%Y-%m-%d %H:%M:%S")
        hace_un_rato = (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            """
            INSERT INTO archivos
            (plano_id, version, autor, fecha, comentarios, ruta_archivo)
            VALUES (?, '1.0', 'EF', ?, 'Primera version', ?)
            """,
            (plano_id_multi, tres_dias, "Detalle_Multi_Archivo_v1.0_S0.pdf"),
        )
        conn.execute(
            """
            INSERT INTO archivos
            (plano_id, version, autor, fecha, comentarios, motivo_subida, ruta_archivo)
            VALUES (?, '1.1', 'EF', ?, 'Pequenas correcciones', 'Revision interna', ?)
            """,
            (plano_id_multi, dia_y_medio, "Detalle_Multi_Archivo_v1.1_S1.pdf"),
        )
        conn.execute(
            """
            INSERT INTO archivos
            (plano_id, version, autor, fecha, comentarios, motivo_subida, ruta_archivo)
            VALUES (?, '2.0', 'GH', ?, 'Aprobacion tecnica', 'Cambio de fase', ?)
            """,
            (plano_id_multi, hace_un_rato, "Detalle_Multi_Archivo_v2.0_S2.pdf"),
        )

        # Sincronizar los campos denormalizados de `planos` con la
        # version mas reciente de archivos. En produccion lo hace
        # automaticamente upload_service.subir_nueva_version cuando la
        # subida es superior; aqui lo hacemos a mano porque el seed
        # inyecta directamente en archivos sin pasar por el servicio.
        conn.execute(
            "UPDATE planos SET version = ?, autor = ?, fecha = ?, tipo_archivo = 'pdf' "
            "WHERE id = ?",
            ("1.1", "AB", un_dia, plano_id_hist),
        )
        conn.execute(
            "UPDATE planos SET version = ?, autor = ?, tipo_archivo = 'pdf' WHERE id = ?",
            ("1.0", "CD", detalle_ids["Detalle_Solo_Archivos"]),
        )
        conn.execute(
            "UPDATE planos SET version = ?, autor = ?, fecha = ?, tipo_archivo = 'pdf' "
            "WHERE id = ?",
            ("2.0", "GH", hace_un_rato, plano_id_multi),
        )

    print(f"[4/4] OK. Proyecto creado en: {folder}")
    print()
    print("Resumen del estado generado:")
    print("  - Obligatorios (sin archivos, sin historial) -> rama 'safe', color GRIS")
    print("  - Detalle_Solo_Archivos (1 archivo, 0 historial) -> 'no_history', color GRIS")
    print("  - Detalle_Con_Historial (2 archivos, 2 historial) -> 'has_history', color S1 amarillo")
    print("  - Detalle_Multi_Archivo (3 archivos, 0 historial) -> color S2 verde")
    print()
    print(f"Para probarlo: arranca la app, selecciona '{PROJECT_CODE}', tipo "
          "'Planos', pulsa '✎ Editar' y prueba a borrar cada plano.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
