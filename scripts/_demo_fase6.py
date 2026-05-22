"""Demo manual: PlanoView abans/despres d'una subida real sobre el seed."""
import sys
import sqlite3
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from controllers.sqlite_planos_controller import SQLitePlanosController  # noqa: E402
from services.upload_service import subir_nueva_version  # noqa: E402

folder = REPO / "PRJ-EDIT_TEST"

ctrl = SQLitePlanosController(folder)
docs = ctrl.get_all_documents()
target = next(d for d in docs if d.codigo == "Detalle_Multi_Archivo")

print("=== ABANS de la subida ===")
print(
    f"  codigo={target.codigo}  estado={target.estado}  "
    f"version={target.current_version}  autor={target.autor}  "
    f"#archivos={len(target.entries)}"
)

tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
tmp.write(b"fake pdf v3.0 content")
tmp.close()

print()
print("=== Subint v3.0 (autor: ZZ, motivo: Demo Fase 6) ===")
result = subir_nueva_version(
    folder,
    target.db_id,
    {"version": "3.0", "autor": "ZZ", "motivo_subida": "Demo Fase 6"},
    Path(tmp.name),
)
print(
    f"  es_version_superior={result['es_version_superior']}  "
    f"estado_nuevo={result['estado_nuevo']}"
)
print(f"  ruta_archivo={result['ruta_archivo']}")

print()
print("=== DESPRES de la subida ===")
docs2 = ctrl.get_all_documents()
target2 = next(d for d in docs2 if d.codigo == "Detalle_Multi_Archivo")
print(
    f"  codigo={target2.codigo}  estado={target2.estado}  "
    f"version={target2.current_version}  autor={target2.autor}  "
    f"#archivos={len(target2.entries)}"
)

db = sqlite3.connect(folder / ".project_manager" / "documents.db")
db.row_factory = sqlite3.Row

print()
print("=== Historial d'estats del plano ===")
for row in db.execute(
    "SELECT estado_anterior, estado_nuevo, cambiado_en "
    "FROM plano_estado_historial WHERE plano_id = ? ORDER BY id",
    (target.db_id,),
):
    print(
        f"  {row['estado_anterior']} -> {row['estado_nuevo']}  "
        f"({row['cambiado_en']})"
    )

print()
print("=== Archivos vinculats al plano (mes recent primer) ===")
for row in db.execute(
    "SELECT version, autor, fecha, motivo_subida, ruta_archivo "
    "FROM archivos WHERE plano_id = ? ORDER BY fecha DESC, id DESC",
    (target.db_id,),
):
    print(
        f"  v{row['version']:<5} autor={(row['autor'] or ''):<4} "
        f"fecha={row['fecha']:<25} motivo={(row['motivo_subida'] or ''):<25} "
        f"ruta={row['ruta_archivo']}"
    )
