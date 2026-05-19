from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from pathlib import Path
import json
import time
import threading
from pydantic import BaseModel, Field, computed_field


class DocumentEntry(BaseModel):
    """A single version/state entry for a document"""
    version: str
    state: str
    timestamp: str
    author: str
    notes: str
    file_path: Optional[str] = None


class Document(BaseModel):
    """
    Document model with Pydantic for performance and validation.
    
    Key Performance Improvements:
    - Pydantic provides automatic validation and serialization
    - Computed fields cache expensive operations
    - Eliminates manual caching and complex validation logic
    
    Updated: Uses Pydantic BaseModel instead of dataclass for better performance
    """
    name: str
    entries: List[DocumentEntry] = Field(default_factory=list)
    autor: str = ""  # Original author - can be edited
    rev_tecnica: str = ""  # Rev. Téc. - First person to correct in S1 state
    rev_gerencia: str = ""  # Rev. Ger. - First person to correct in S2 state

    @computed_field
    @property
    def id(self) -> str:
        """Document ID is the name for backward compatibility"""
        return self.name

    @computed_field
    @property
    def current_entry(self) -> Optional[DocumentEntry]:
        """Get the most recent entry (by timestamp)"""
        if not self.entries:
            return None
        return max(self.entries, key=lambda x: x.timestamp)

    @computed_field
    @property
    def current_version(self) -> str:
        """Get current version from the latest entry"""
        current = self.current_entry
        return current.version if current else ""

    @computed_field
    @property
    def current_state(self) -> str:
        """Get current state from the latest entry"""
        current = self.current_entry
        return current.state if current else ""

    @computed_field
    @property
    def version(self) -> str:
        """Alias for current_version for backward compatibility"""
        return self.current_version

    @computed_field
    @property
    def filename(self) -> str:
        """Generate filename from current document state"""
        if not self.entries:
            return f"{self.name}.pdf"
        
        current = self.current_entry
        if not current:
            return f"{self.name}.pdf"
        
        # Generate filename: name_version.pdf (no state in filename)
        safe_name = self.name.replace(" ", "_").replace("/", "_")
        return f"{safe_name}_{current.version}.pdf"

    @computed_field
    @property
    def latest_notes(self) -> str:
        """Get notes from the latest entry"""
        current = self.current_entry
        return current.notes if current else ""

    @computed_field
    @property
    def creation_date(self) -> str:
        """Get creation date from the earliest entry"""
        if not self.entries:
            return ""
        earliest = min(self.entries, key=lambda x: x.timestamp)
        return earliest.timestamp

    def add_entry(self, version: str, state: str, author: str, notes: str) -> None:
        """Add a new version/state entry"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = DocumentEntry(
            version=version,
            state=state,
            timestamp=timestamp,
            author=author,
            notes=notes
        )
        self.entries.append(entry)

    def get_entries_by_state(self, state: str) -> List[DocumentEntry]:
        """Get all entries with a specific state"""
        return [entry for entry in self.entries if entry.state == state]

    def get_entries_by_version(self, version: str) -> List[DocumentEntry]:
        """Get all entries with a specific version"""
        return [entry for entry in self.entries if entry.version == version]


class DocumentRepository:
    """Repository for managing documents with thread safety"""
    
    def __init__(self, manifest_path: Path):
        self.manifest_path = manifest_path
        self.documents: Dict[str, Document] = {}
        self._lock = threading.Lock()
        self._last_modified = 0
        self.load()
    
    def load(self) -> None:
        """Load documents from manifest file"""
        with self._lock:
            try:
                if self.manifest_path.exists():
                    self._last_modified = self.manifest_path.stat().st_mtime
                    with open(self.manifest_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    self.documents = {}
                    for doc_name, doc_data in data.items():
                        # Convert entries to DocumentEntry objects
                        entries = [DocumentEntry(**entry) for entry in doc_data.get('entries', [])]
                        doc_data['entries'] = entries
                        self.documents[doc_name] = Document(**doc_data)
                else:
                    self.documents = {}
            except Exception as e:
                print(f"Error loading documents: {e}")
                self.documents = {}
    
    def save(self) -> None:
        """Save documents to manifest file"""
        with self._lock:
            try:
                # Ensure parent directory exists
                self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
                
                # Convert to serializable format
                data = {}
                for doc_name, document in self.documents.items():
                    data[doc_name] = document.model_dump()
                
                with open(self.manifest_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                
                self._last_modified = self.manifest_path.stat().st_mtime
            except Exception as e:
                print(f"Error saving documents: {e}")
    
    def reload(self) -> None:
        """Reload documents if the file has been modified"""
        try:
            if self.manifest_path.exists():
                current_modified = self.manifest_path.stat().st_mtime
                if current_modified > self._last_modified:
                    self.load()
        except Exception:
            pass  # Continue with current data if reload fails
    
    def add_document(self, document: Document) -> None:
        """Add a new document"""
        with self._lock:
            self.documents[document.name] = document
            self.save()
    
    def update_document(self, doc_name: str, document: Document) -> None:
        """Update an existing document"""
        with self._lock:
            self.documents[doc_name] = document
            self.save()
    
    def get_document(self, doc_name: str) -> Optional[Document]:
        """Get a document by name"""
        return self.documents.get(doc_name)
    
    def get_all_documents(self) -> List[Document]:
        """Get all documents"""
        return list(self.documents.values())
    
    def document_exists(self, doc_name: str) -> bool:
        """Check if a document exists"""
        return doc_name in self.documents
    
    def delete_document(self, doc_name: str) -> bool:
        """Delete a document"""
        with self._lock:
            if doc_name in self.documents:
                del self.documents[doc_name]
                self.save()
                return True
            return False