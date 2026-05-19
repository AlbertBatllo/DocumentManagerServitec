"""Soft-delete helper: move files to a project-local recycle bin folder.

Files are moved to <project_path>/_PAPELERA/ instead of being unlinked, so
the user can recover them by moving them back manually. The database entry
is still removed by the caller; only the file recovery is automatic.
"""

from datetime import datetime
from pathlib import Path
import shutil

TRASH_FOLDER_NAME = "_PAPELERA"


def move_to_trash(file_path: Path, project_path: Path) -> Path:
    """Move ``file_path`` into ``project_path/_PAPELERA/`` and return the new path.

    On name collision, append a timestamp to the stem so previously deleted
    files are not overwritten.
    """
    file_path = Path(file_path)
    project_path = Path(project_path)

    if not file_path.exists():
        raise FileNotFoundError(str(file_path))

    trash_dir = project_path / TRASH_FOLDER_NAME
    trash_dir.mkdir(parents=True, exist_ok=True)

    target = trash_dir / file_path.name
    if target.exists():
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = trash_dir / f"{file_path.stem}__{ts}{file_path.suffix}"
        if target.exists():
            counter = 1
            while True:
                candidate = trash_dir / f"{file_path.stem}__{ts}_{counter}{file_path.suffix}"
                if not candidate.exists():
                    target = candidate
                    break
                counter += 1

    shutil.move(str(file_path), str(target))
    return target
