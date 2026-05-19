"""
Resolució dinàmica de carpetes de documents dins d'un projecte.

Els projectes reals poden tenir noms de carpeta variats:
  - 02_Planos, 06_Planos, 06.-PLANOS, 06.- PLANOS, etc.
  - 03_Presupuestos, 03.-PRESUPUESTOS, etc.
  - 04_Certificaciones, 04.-CERTIFICACIONES, etc.

FolderResolver localitza la carpeta correcta cercant noms coneguts
i fent fallback amb glob si cal.
"""

import re
from pathlib import Path
from typing import Dict, Optional


__all__ = ["FolderResolver"]


# Known folder name patterns per document type, ordered by priority
_KNOWN_NAMES: Dict[str, list] = {
    "planos": [
        "02_Planos",
        "06_Planos",
        "06.-PLANOS",
        "06.- PLANOS",
        "06_PLANOS",
        "02.-PLANOS",
        "02.- PLANOS",
        "Planos",
        "PLANOS",
    ],
    "presupuestos": [
        "03_Presupuestos",
        "03.-PRESUPUESTOS",
        "03.- PRESUPUESTOS",
        "Presupuestos",
        "PRESUPUESTOS",
    ],
    "certificaciones": [
        "04_Certificaciones",
        "04.-CERTIFICACIONES",
        "04.- CERTIFICACIONES",
        "Certificaciones",
        "CERTIFICACIONES",
    ],
}

# Glob fallback patterns per document type
_GLOB_PATTERNS: Dict[str, list] = {
    "planos": ["*[Pp]lanos*", "*PLANOS*"],
    "presupuestos": ["*[Pp]resupuestos*", "*PRESUPUESTOS*"],
    "certificaciones": ["*[Cc]ertificaciones*", "*CERTIFICACIONES*"],
}

# Default folder names (used when nothing is found on disk)
_DEFAULTS: Dict[str, str] = {
    "planos": "02_Planos",
    "presupuestos": "03_Presupuestos",
    "certificaciones": "04_Certificaciones",
}

# Regex to identify a planos folder name in path parts
_PLANOS_PATTERN = re.compile(r"planos", re.IGNORECASE)


class FolderResolver:
    """Resolves document folder paths dynamically within a project."""

    _cache: Dict[str, Path] = {}

    @classmethod
    def resolve(cls, project_path, doc_type: str = "planos") -> Path:
        """
        Resolve the folder path for a given document type within a project.

        Args:
            project_path: Path to the project root directory.
            doc_type: One of 'planos', 'presupuestos', 'certificaciones'.

        Returns:
            Path to the resolved folder. Falls back to a default name
            if no matching folder is found on disk.
        """
        project_path = Path(project_path)
        cache_key = f"{project_path}::{doc_type}"

        if cache_key in cls._cache:
            return cls._cache[cache_key]

        resolved = cls._search_folder(project_path, doc_type)
        cls._cache[cache_key] = resolved
        return resolved

    @classmethod
    def resolve_planos(cls, project_path) -> Path:
        """Shortcut for resolve(project_path, 'planos')."""
        return cls.resolve(project_path, "planos")

    @classmethod
    def resolve_presupuestos(cls, project_path) -> Path:
        """Shortcut for resolve(project_path, 'presupuestos')."""
        return cls.resolve(project_path, "presupuestos")

    @classmethod
    def resolve_certificaciones(cls, project_path) -> Path:
        """Shortcut for resolve(project_path, 'certificaciones')."""
        return cls.resolve(project_path, "certificaciones")

    @classmethod
    def clear_cache(cls) -> None:
        """Clear all cached folder resolutions."""
        cls._cache.clear()

    @classmethod
    def is_planos_folder(cls, folder_name: str) -> bool:
        """Check if a folder name matches a planos-type folder."""
        return bool(_PLANOS_PATTERN.search(folder_name))

    @classmethod
    def _folder_has_content(cls, folder: Path) -> bool:
        """Check if a folder has real content (files or subdirectories)."""
        try:
            return any(folder.iterdir())
        except OSError:
            return False

    @classmethod
    def _get_real_dirs(cls, project_path: Path) -> dict:
        """
        Get a map of lowercase folder names to their real Path on disk.
        This ensures we return actual disk names (correct casing on Windows).
        """
        result = {}
        try:
            for entry in project_path.iterdir():
                if entry.is_dir():
                    result[entry.name.lower()] = entry
        except OSError:
            pass
        return result

    @classmethod
    def _search_folder(cls, project_path: Path, doc_type: str) -> Path:
        """
        Search for an existing folder matching the document type.

        Strategy:
        1. Scan actual directories on disk (preserves real casing).
        2. Match against known names (case-insensitive on Windows).
        3. If multiple match, prefer the one with content (non-empty).
        4. Fallback: glob for partial matches (prefer non-empty).
        5. Final fallback: return default name (may not exist on disk).
        """
        # Get actual directory listing with real names from disk
        real_dirs = cls._get_real_dirs(project_path)

        # Match known names against actual directories
        known_names = _KNOWN_NAMES.get(doc_type, [])
        found_candidates = []
        seen_lower = set()
        for name in known_names:
            name_lower = name.lower()
            if name_lower in real_dirs and name_lower not in seen_lower:
                seen_lower.add(name_lower)
                found_candidates.append(real_dirs[name_lower])

        if found_candidates:
            # If only one exists, return it
            if len(found_candidates) == 1:
                return found_candidates[0]
            # Multiple exist: prefer the one with real content
            for candidate in found_candidates:
                if cls._folder_has_content(candidate):
                    return candidate
            # All empty: return the first one
            return found_candidates[0]

        # Glob fallback
        glob_patterns = _GLOB_PATTERNS.get(doc_type, [])
        for pattern in glob_patterns:
            try:
                matches = [
                    p for p in project_path.glob(pattern)
                    if p.is_dir()
                ]
                if matches:
                    # Prefer non-empty folder
                    for m in matches:
                        if cls._folder_has_content(m):
                            return m
                    return matches[0]
            except OSError:
                continue

        # Nothing found on disk — return default path
        default_name = _DEFAULTS.get(doc_type, f"02_{doc_type.capitalize()}")
        return project_path / default_name
