from pathlib import Path


class ProjectUtils:
    @staticmethod
    def get_project_name() -> str:
        current_path = Path.cwd()
        parent_name = current_path.parent.name
        current_name = current_path.name
        
        if parent_name and current_name:
            return f"{parent_name}/{current_name}"
        elif current_name:
            return current_name
        else:
            return "Proyecto Sin Nombre"

    @staticmethod
    def ensure_directory_exists(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)

