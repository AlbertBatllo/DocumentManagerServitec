"""
Helpers para localizar rutas importantes de la aplicacion.

`get_projects_root()` devuelve la carpeta donde la app busca y crea
proyectos. Es la misma logica que usaba `project_selection_view.py` para
descubrir carpetas `PRJ-*`, extraida aqui para que el flujo de creacion
de proyectos (Fase 2) la pueda reutilizar sin duplicar.

Reglas:
    - Modo desarrollo (no congelado): cwd al ejecutar la app.
    - Modo PyInstaller en macOS: 4 niveles por encima del ejecutable
      (carpeta que contiene el .app).
    - Modo PyInstaller en Windows: la carpeta del .exe, o su padre si
      la del exe no contiene PRJ-* (caso --onedir).
    - Modo PyInstaller en Linux: la carpeta del ejecutable.
"""

import sys
from pathlib import Path


def get_projects_root() -> Path:
    """Devuelve la carpeta donde la app lista y crea proyectos."""
    if not getattr(sys, "frozen", False):
        return Path.cwd()

    if sys.platform == "darwin":
        return Path(sys.executable).parent.parent.parent.parent

    if sys.platform == "win32":
        exe_dir = Path(sys.executable).parent
        try:
            children = list(exe_dir.iterdir())
        except OSError:
            return exe_dir
        # En builds --onedir el exe vive dentro de DocumentManager/ y los
        # PRJ-* estan en el padre. Detectamos eso comprobando si exe_dir
        # tiene contenido pero no PRJ-*.
        has_content = bool(children)
        has_prj = any(p.name.startswith("PRJ") and p.is_dir() for p in children)
        if has_content and not has_prj:
            return exe_dir.parent
        return exe_dir

    return Path(sys.executable).parent
