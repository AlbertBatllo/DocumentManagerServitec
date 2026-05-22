"""Demo manual: bulk upload sobre el seed (3 arxius: 2 nuevos + 1 versio)."""
import sys
import sqlite3
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from controllers.sqlite_planos_controller import SQLitePlanosController  # noqa: E402
from services.upload_service import subir_masivo  # noqa: E402

folder = REPO / "PRJ-EDIT_TEST"


def make_tmp(name_hint: str) -> Path:
    f = tempfile.NamedTemporaryFile(
        suffix=".pdf", prefix=name_hint + "_", delete=False
    )
    f.write(b"fake content for demo")
    f.close()
    return Path(f.name)


print("=== ABANS del bulk ===")
ctrl = SQLitePlanosController(folder)
docs = ctrl.get_all_documents()
print(f"  total docs: {len(docs)}")
for d in docs:
    print(
        f"    codigo={d.codigo:<28} estado={d.estado:<8} "
        f"version={d.current_version or '-':<6} #archivos={len(d.entries)}"
    )

# 3 items:
#  - Plano_Demo_Nuevo_1 (codigo inexistent)
#  - Plano_Demo_Nuevo_2 (codigo inexistent)
#  - Detalle_Multi_Archivo (codigo existent al seed; pujem v3.0 superior a 2.0)
items = [
    {
        "archivo_path": make_tmp("demo_nuevo_1"),
        "form_data": {
            "codigo": "Plano_Demo_Nuevo_1", "nombre": "Plano Demo Nou 1",
            "version": "1.0", "autor": "DD", "comentarios": "Demo bulk 1",
        },
    },
    {
        "archivo_path": make_tmp("demo_nuevo_2"),
        "form_data": {
            "codigo": "Plano_Demo_Nuevo_2", "nombre": "Plano Demo Nou 2",
            "version": "1.0", "autor": "DD", "comentarios": "Demo bulk 2",
        },
    },
    {
        "archivo_path": make_tmp("multi_v3"),
        "form_data": {
            "codigo": "Detalle_Multi_Archivo", "version": "3.0",
            "autor": "DD", "motivo_subida": "Demo bulk Fase 7",
        },
    },
]

print()
print("=== Cridant subir_masivo (3 items) ===")
results = subir_masivo(folder, items)

print()
print("=== Resultats per item ===")
for r in results:
    print(
        f"  archivo={r['archivo']:<55} codigo={r['codigo']:<28} "
        f"resultat={r['resultat']:<8} detalls={r['detalls']}"
    )

print()
print("=== DESPRES del bulk ===")
docs2 = ctrl.get_all_documents()
print(f"  total docs: {len(docs2)}")
for d in docs2:
    print(
        f"    codigo={d.codigo:<28} estado={d.estado:<8} "
        f"version={d.current_version or '-':<6} #archivos={len(d.entries)}"
    )
