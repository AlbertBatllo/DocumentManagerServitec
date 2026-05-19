from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import json
from pydantic import BaseModel, Field, computed_field


# Planos status codes (standardized across all document types)
PLANO_STATES = [
    "S0",  # Borrador
    "S1",  # Revisado por Delineación
    "S2",  # Revisado por Técnico Especialista
    "S3",  # Revisado por Director Proyecto
    "S3A", # Aprobado por propiedad/promotor
    "D"    # Denegado
]

STATE_DISPLAY_NAMES = {
    "S0": "Borrador",
    "S1": "Revisado por Delineación", 
    "S2": "Revisado por Técnico Especialista",
    "S3": "Revisado por Director Proyecto",
    "S3A": "Aprobado por propiedad/promotor",
    "D": "Denegado"
}


class PlanoDocumentEntry(BaseModel):
    """A single version entry for a plano document"""
    version: str
    state: str
    timestamp: str
    author: str
    rev_tecnica: str = ""
    rev_gerencia: str = ""
    notes: str = ""
    file_path: Optional[str] = None


class PlanoDocument(BaseModel):
    """
    Plano document with Pydantic for performance and validation.
    
    Key Performance Improvements:
    - Pydantic provides automatic validation and serialization
    - Computed fields cache expensive operations automatically
    - Eliminates manual caching and complex validation logic
    
    Updated: Uses Pydantic BaseModel instead of dataclass for better performance
    """
    name: str
    entries: List[PlanoDocumentEntry] = Field(default_factory=list)

    @computed_field
    @property
    def id(self) -> str:
        """Alias for name for backwards compatibility"""
        return self.name

    @computed_field
    @property
    def _sorted_entries(self) -> List[PlanoDocumentEntry]:
        """Get entries sorted by timestamp (newest first) - cached by Pydantic"""
        if not self.entries:
            return []
        return sorted(self.entries, key=lambda x: x.timestamp, reverse=True)
    
    @computed_field
    @property
    def current_version(self) -> str:
        """Get the latest version from all entries"""
        if not self._sorted_entries:
            return "1.0"
        return self._sorted_entries[0].version

    @computed_field
    @property
    def current_state(self) -> str:
        """Get the latest state for the current version"""
        if not self._sorted_entries:
            return "S0"
        
        current_ver = self.current_version
        current_version_entries = [e for e in self._sorted_entries if e.version == current_ver]
        if not current_version_entries:
            return "S0"
        
        return current_version_entries[0].state

    @computed_field
    @property
    def version(self) -> str:
        """Alias for current_version for compatibility"""
        return self.current_version

    @computed_field
    @property
    def latest_entry(self) -> Optional[PlanoDocumentEntry]:
        """Get the most recent entry"""
        return self._sorted_entries[0] if self._sorted_entries else None
    
    @computed_field
    @property
    def earliest_entry(self) -> Optional[PlanoDocumentEntry]:
        """Get the earliest entry"""
        if not self.entries:
            return None
        return sorted(self.entries, key=lambda x: x.timestamp)[0]

    @computed_field
    @property
    def latest_notes(self) -> str:
        """Get notes from the most recent entry"""
        return self.latest_entry.notes if self.latest_entry else ""
    
    @computed_field
    @property
    def creation_date(self) -> str:
        """Get document creation date in DD/MM/YYYY format"""
        try:
            earliest = self.earliest_entry
            if earliest:
                timestamp = datetime.fromisoformat(earliest.timestamp.replace('Z', '+00:00'))
                return timestamp.strftime("%d/%m/%Y")
            else:
                return datetime.now().strftime("%d/%m/%Y")
        except Exception:
            return ""

    @computed_field
    @property
    def autor(self) -> str:
        """Get the author of the latest entry"""
        if not self._sorted_entries:
            return ""
        
        current_ver = self.current_version
        current_version_entries = [e for e in self._sorted_entries if e.version == current_ver]
        if not current_version_entries:
            return ""
        
        return current_version_entries[0].author

    @computed_field
    @property
    def rev_tecnica(self) -> str:
        """Get the technical reviewer of the latest entry"""
        if not self._sorted_entries:
            return ""
        
        current_ver = self.current_version
        current_version_entries = [e for e in self._sorted_entries if e.version == current_ver]
        if not current_version_entries:
            return ""
        
        return current_version_entries[0].rev_tecnica

    @computed_field
    @property
    def rev_gerencia(self) -> str:
        """Get the management reviewer of the latest entry"""
        if not self._sorted_entries:
            return ""
        
        current_ver = self.current_version
        current_version_entries = [e for e in self._sorted_entries if e.version == current_ver]
        if not current_version_entries:
            return ""
        
        return current_version_entries[0].rev_gerencia

    def add_entry(self, version: str, state: str, author: str, rev_tecnica: str = "", 
                  rev_gerencia: str = "", notes: str = "") -> None:
        """Add a new version/state entry"""
        if state not in PLANO_STATES:
            raise ValueError(f"State '{state}' no válido. Debe ser uno de: {PLANO_STATES}")
        
        entry = PlanoDocumentEntry(
            version=version,
            state=state,
            timestamp=datetime.now().strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            author=author,
            rev_tecnica=rev_tecnica,
            rev_gerencia=rev_gerencia,
            notes=notes
        )
        self.entries.append(entry)

    def get_state_display_name(self, state: str = None) -> str:
        """Get display name for state"""
        state_to_check = state or self.current_state
        return STATE_DISPLAY_NAMES.get(state_to_check, state_to_check)

    def get_all_versions(self) -> List[str]:
        """Get all unique versions, sorted"""
        versions = list(set(entry.version for entry in self.entries))
        return sorted(versions, reverse=True)

    def get_entries_for_version(self, version: str) -> List[PlanoDocumentEntry]:
        """Get all entries for a specific version, sorted by timestamp"""
        version_entries = [e for e in self.entries if e.version == version]
        return sorted(version_entries, key=lambda x: x.timestamp)

    def get_version_history(self) -> List[Dict[str, Any]]:
        """Get version history in a format compatible with the UI"""
        history = []
        for entry in sorted(self.entries, key=lambda x: x.timestamp):
            history.append({
                'version': entry.version,
                'state': entry.state,
                'date': entry.timestamp[:10] if entry.timestamp else "",
                'author': entry.author,
                'rev_tecnica': entry.rev_tecnica,
                'rev_gerencia': entry.rev_gerencia,
                'notes': entry.notes
            })
        return history

    def to_dict(self) -> Dict[str, Any]:
        """For backward compatibility - use model_dump() instead"""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PlanoDocument':
        """For backward compatibility - create from legacy data format"""
        # Support both old format (with id) and new format (name only)
        name = data.get("name") or data.get("id", "")
        
        # Handle legacy entry format
        entries_data = data.get("entries", [])
        entries = []
        for entry_data in entries_data:
            # Ensure all required fields are present
            entry_dict = {
                "version": entry_data.get("version", "1.0"),
                "state": entry_data.get("state", "S0"),
                "timestamp": entry_data.get("timestamp", datetime.now().isoformat() + "Z"),
                "author": entry_data.get("author", ""),
                "rev_tecnica": entry_data.get("rev_tecnica", ""),
                "rev_gerencia": entry_data.get("rev_gerencia", ""),
                "notes": entry_data.get("notes", "")
            }
            entries.append(PlanoDocumentEntry(**entry_dict))
        
        return cls(name=name, entries=entries)


class PlanoRepository:
    """Repository for managing plano documents"""
    
    # Class-level cache to avoid reloading same data
    _instances_cache: Dict[str, 'PlanoRepository'] = {}
    _last_load_time: Dict[str, float] = {}
    
    def __new__(cls, manifest_path: Path):
        """Singleton pattern per manifest_path to avoid multiple loads"""
        path_str = str(manifest_path)
        if path_str not in cls._instances_cache:
            instance = super().__new__(cls)
            cls._instances_cache[path_str] = instance
        return cls._instances_cache[path_str]
    
    def __init__(self, manifest_path: Path):
        path_str = str(manifest_path)
        # Only initialize once
        if not hasattr(self, '_initialized'):
            self.manifest_path = manifest_path
            self.documents: Dict[str, PlanoDocument] = {}
            self._initialized = True
            self.load()

    def load(self) -> None:
        """Load documents from manifest file with caching"""
        import time
        path_str = str(self.manifest_path)
        
        try:
            # Check if file was modified since last load
            current_mtime = self.manifest_path.stat().st_mtime if self.manifest_path.exists() else 0
            last_load = self._last_load_time.get(path_str, 0)
            
            # Skip reload if file hasn't changed (with 1 second tolerance)
            if last_load > 0 and abs(current_mtime - last_load) < 1:
                return
            
            from utils.file_manager import FileManager
            data = FileManager.safe_json_read(str(self.manifest_path))
            
            # Clear and reload
            self.documents.clear()
            
            # Handle both old format (id-based keys) and new format (name-based keys)
            for key, doc_data in data.items():
                document = PlanoDocument.from_dict(doc_data)
                # Use the document's name as the key
                self.documents[document.name] = document
            
            # Update last load time
            self._last_load_time[path_str] = current_mtime
            
        except Exception as e:
            print(f"Error loading plano data: {e}")
            if not self.documents:
                self.documents = {}

    def save(self) -> None:
        """Save documents to manifest file"""
        try:
            from utils.file_manager import FileManager
            data = {doc_name: doc.model_dump() for doc_name, doc in self.documents.items()}
            FileManager.safe_json_write(str(self.manifest_path), data)
        except Exception as e:
            print(f"Error saving plano data: {e}")
            raise

    def add_document(self, document: PlanoDocument) -> None:
        """Add a new document"""
        self.documents[document.name] = document
        self.save()

    def get_document(self, doc_name: str) -> Optional[PlanoDocument]:
        """Get document by name"""
        return self.documents.get(doc_name)
    
    def get_document_by_name(self, doc_name: str) -> Optional[PlanoDocument]:
        """Alias for get_document for clarity"""
        return self.get_document(doc_name)

    def update_document(self, doc_name: str, document: PlanoDocument) -> None:
        """Update existing document"""
        self.documents[doc_name] = document
        self.save()

    def get_all_documents(self) -> List[PlanoDocument]:
        """Get all documents"""
        return list(self.documents.values())

    def document_exists(self, doc_name: str) -> bool:
        """Check if document exists"""
        return doc_name in self.documents

    def get_documents_by_state(self, state: str) -> List[PlanoDocument]:
        """Get all documents in a specific state"""
        return [doc for doc in self.documents.values() if doc.current_state == state]

    def get_state_status_summary(self) -> Dict[str, int]:
        """Get summary of document counts per state"""
        summary = {state: 0 for state in PLANO_STATES}
        
        for doc in self.documents.values():
            if doc.current_state in summary:
                summary[doc.current_state] += 1
        
        return summary
    
    def find_similar_documents(self, query: str, max_results: int = 5) -> List[PlanoDocument]:
        """Find documents with names similar to the query using fuzzy matching"""
        from utils.fuzzy_matcher import default_matcher
        
        all_names = list(self.documents.keys())
        similar_names = default_matcher.find_similar_names(query, all_names)
        
        results = []
        for name, score in similar_names[:max_results]:
            if name in self.documents:
                results.append(self.documents[name])
        
        return results
    
    def check_duplicate_name(self, name: str) -> Optional[str]:
        """Check if a name is too similar to existing documents. Returns conflicting name if found."""
        from utils.fuzzy_matcher import default_matcher
        
        for existing_name in self.documents.keys():
            if default_matcher.is_potential_duplicate(name, existing_name):
                return existing_name
        
        return None