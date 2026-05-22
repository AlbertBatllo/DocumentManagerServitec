"""
SQLite-backed Document models.
Maintains compatibility with existing Document model API while using SQLite storage.
"""

import sqlite3
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from pathlib import Path
import sqlite3
from pydantic import BaseModel, Field, computed_field
from models.document import DocumentEntry


class SQLiteDocument(BaseModel):
    """
    SQLite-backed document model.
    
    Maintains the same API as the original Document model but stores data in SQLite.
    Uses the simplest possible approach - just replace JSON operations with SQLite.
    """
    
    # Database fields
    db_id: Optional[int] = Field(default=None, alias='id')  # SQLite row ID
    name: str  # Document identifier (used as primary key for loading)
    display_name: str = ""  # Human-readable display name
    document_type: str = ""  # planos, certificaciones, licitaciones
    entries: List[DocumentEntry] = Field(default_factory=list)
    autor: str = ""  # Original author - can be edited
    rev_tecnica: str = ""  # Rev. Téc. - First person to correct in S1 state
    rev_gerencia: str = ""  # Rev. Ger. - First person to correct in S2 state
    file_paths: List[str] = Field(default_factory=list)  # Associated file paths for efficient operations
    project_phase: str = "Implantación"  # Project phase: Implantación, Proyecto Básico, Proyecto Ejecutivo, Dirección Obra
    associated_dwg: str = ""  # Path to associated DWG file (one DWG can contain multiple layouts)
    # Estado del plano segun el nuevo modelo (GRIS/BLANCO/S1/S2/S3/ROJO/NARANJA).
    # NO se persiste desde aqui: lo lee el SQLitePlanosController desde la tabla
    # `planos` (Fase 1) y lo adjunta al documento para que el dashboard pueda
    # pintar la fila con el color correcto (Fase 5, utils/estados.py).
    estado: str = ""
    
    # Keep track of database manager for operations
    db_manager: Optional[Any] = Field(default=None, exclude=True)
    user_name: Optional[str] = Field(default=None, exclude=True)
    
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
        """Generate filename matching local PDF format with version and state"""
        if not self.entries:
            return f"{self.name.replace(' ', '_')}_unknown.pdf"

        current = self.current_entry
        if not current:
            return f"{self.name.replace(' ', '_')}_unknown.pdf"

        # Generate filename with version AND state: name_vX.X_STATE.pdf
        safe_name = self.name.replace(" ", "_").replace("/", "_")
        safe_version = current.version.replace(" ", "_").replace("/", "_")
        state = current.state
        return f"{safe_name}_{safe_version}_{state}.pdf"

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

    def add_entry(self, version: str, state: str, author: str, 
                  rev_tecnica: str = "", rev_gerencia: str = "", 
                  notes: str = "", timestamp: str = None, file_path: str = None) -> None:
        """Add a new entry to the document"""
        if not timestamp:
            timestamp = datetime.now().isoformat()
            
        entry = DocumentEntry(
            version=version,
            state=state,
            timestamp=timestamp,
            author=author,
            notes=notes,
            file_path=file_path
        )
        
        self.entries.append(entry)
        
        # Also add to document-level file_paths list if provided
        if file_path and file_path not in self.file_paths:
            self.file_paths.append(file_path)
        
        # Update rev fields if they're being set for the first time
        if rev_tecnica and not self.rev_tecnica:
            self.rev_tecnica = rev_tecnica
        if rev_gerencia and not self.rev_gerencia:
            self.rev_gerencia = rev_gerencia

    def add_file_path(self, file_path: str) -> None:
        """Add a file path to the document's tracked files"""
        if file_path not in self.file_paths:
            self.file_paths.append(file_path)

    def remove_file_path(self, file_path: str) -> bool:
        """Remove a file path from the document's tracked files. Returns True if removed."""
        if file_path in self.file_paths:
            self.file_paths.remove(file_path)
            return True
        return False

    def get_file_paths(self) -> List[str]:
        """Get all tracked file paths for this document"""
        return self.file_paths.copy()

    def get_state_display_name(self, state: str = None) -> str:
        """Get display name for state (compatible with PlanoDocument API)"""
        from models.plano_document import STATE_DISPLAY_NAMES
        state_to_check = state or self.current_state
        return STATE_DISPLAY_NAMES.get(state_to_check, state_to_check)

    def update_file_path(self, old_path: str, new_path: str) -> bool:
        """Update a file path (useful for renames). Returns True if updated."""
        if old_path in self.file_paths:
            index = self.file_paths.index(old_path)
            self.file_paths[index] = new_path
            return True
        return False

    def save_to_database(self) -> None:
        """
        Save document to SQLite database.
        This is the key method that replaces JSON file operations.
        """
        if not self.db_manager:
            raise ValueError("Database manager not set - cannot save document")
        if not self.user_name:
            raise ValueError("User name not set - cannot save document")
        if not self.document_type:
            raise ValueError("Document type not set - cannot save document")
        # Simplified approach: use standard database operations without complex locking
        # Thread-local connections handle concurrency safely
        
        # Save document data
        # Ensure all values are actual values, not property objects
        document_data = {
            'current_version': str(self.current_version) if self.current_version else '',
            'current_state': str(self.current_state) if self.current_state else '',
            'autor': str(self.autor) if self.autor else '',
            'rev_tecnica': str(self.rev_tecnica) if self.rev_tecnica else '',
            'rev_gerencia': str(self.rev_gerencia) if self.rev_gerencia else '',
            'file_paths': list(self.file_paths) if self.file_paths else [],
            'project_phase': str(self.project_phase) if self.project_phase else 'Implantación',
            'associated_dwg': str(self.associated_dwg) if self.associated_dwg else ''
        }
        
        # Save using standard method (which uses its own transaction)
        saved_db_id = self.db_manager.save_document(
            self.document_type, 
            self.name, 
            document_data, 
            self.user_name
        )
        
        # Update our db_id
        if not self.db_id:
            self.db_id = saved_db_id
        elif self.db_id != saved_db_id:
            self.db_id = saved_db_id
        
        # Save entries - be smart about avoiding duplicates
        if self.entries:
            existing_entries = self._get_existing_entries()
            
            # For new documents (no existing entries), save all entries
            if not existing_entries:
                for entry in self.entries:
                    entry_data = {
                        'version': entry.version,
                        'state': entry.state,
                        'author': entry.author,
                        'notes': entry.notes,
                        'timestamp': entry.timestamp
                    }
                    self.db_manager.add_document_entry(self.db_id, entry_data)
            else:
                # For existing documents, only save new entries
                for entry in self.entries:
                    if not self._entry_exists(entry, existing_entries):
                        entry_data = {
                            'version': entry.version,
                            'state': entry.state,
                            'author': entry.author,
                            'notes': entry.notes,
                            'timestamp': entry.timestamp
                        }
                        self.db_manager.add_document_entry(self.db_id, entry_data)

    def _get_existing_entries(self) -> List[Dict[str, str]]:
        """Get existing entries from database to avoid duplicates"""
        try:
            with self.db_manager.connection() as conn:
                # Commit any pending transactions to ensure we see all data
                try:
                    conn.commit()
                except (sqlite3.Error, sqlite3.OperationalError) as e:
                    from utils.error_logger import logger
                    logger.warning(f"Could not commit database changes during entry retrieval", {"document_id": self.db_id, "error": str(e)})
                    
                cursor = conn.execute("""
                    SELECT version, state, author, notes, timestamp
                    FROM document_entries 
                    WHERE document_id = ?
                    ORDER BY timestamp
                """, (self.db_id,))
                
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
                
        except Exception as e:
            from utils.error_logger import logger
            logger.error(f"Failed to get existing entries for document", e, {"document_id": self.db_id})
            return []
    
    def _entry_exists(self, new_entry: DocumentEntry, existing_entries: List[Dict[str, str]]) -> bool:
        """Check if an entry already exists in database"""
        from datetime import datetime
        
        for existing in existing_entries:
            if (existing['version'] == new_entry.version and 
                existing['state'] == new_entry.state and
                existing['author'] == new_entry.author):
                
                # Compare timestamps more flexibly to handle format differences
                try:
                    # Normalize timestamps for comparison
                    new_ts = new_entry.timestamp
                    existing_ts = existing['timestamp']
                    
                    # Parse both timestamps and compare as datetime objects
                    if 'T' in new_ts:
                        new_dt = datetime.fromisoformat(new_ts.replace('Z', '+00:00'))
                    else:
                        new_dt = datetime.strptime(new_ts, '%Y-%m-%d %H:%M:%S')
                    
                    if 'T' in existing_ts:
                        existing_dt = datetime.fromisoformat(existing_ts.replace('Z', '+00:00'))
                    else:
                        existing_dt = datetime.strptime(existing_ts, '%Y-%m-%d %H:%M:%S')
                    
                    # Consider entries the same if they're within 1 second of each other
                    # (to handle minor timestamp differences)
                    time_diff = abs((new_dt - existing_dt).total_seconds())
                    if time_diff < 1.0:
                        return True
                        
                except (ValueError, TypeError):
                    # If timestamp parsing fails, fall back to string comparison
                    if existing['timestamp'] == new_entry.timestamp:
                        return True
        return False

    @classmethod
    def load_from_database(cls, db_manager, doc_type: str, name: str, user_name: str) -> Optional['SQLiteDocument']:
        """
        Load document from SQLite database.
        This replaces JSON file reading operations.
        """
        try:
            # Get document by type and name
            with db_manager.connection() as conn:
                cursor = conn.execute("""
                    SELECT * FROM documents 
                    WHERE document_type = ? AND name = ?
                """, (doc_type, name))
                
                row = cursor.fetchone()
                if not row:
                    return None
                
                doc_dict = dict(row)
                
                # Get entries for this document
                entries_cursor = conn.execute("""
                    SELECT version, state, author, notes, timestamp
                    FROM document_entries 
                    WHERE document_id = ?
                    ORDER BY timestamp
                """, (doc_dict['id'],))
            
            entries = []
            for entry_row in entries_cursor.fetchall():
                entry_dict = dict(entry_row)
                entries.append(DocumentEntry(**entry_dict))
            
            # Parse file_paths from JSON (handle missing column gracefully)
            import json
            file_paths = []
            try:
                file_paths_str = doc_dict.get('file_paths', '[]')
                if file_paths_str:
                    file_paths = json.loads(file_paths_str)
                else:
                    file_paths = []
            except (json.JSONDecodeError, TypeError, KeyError):
                # Handle cases where file_paths column doesn't exist or has invalid data
                file_paths = []
            
            # Create document
            document = cls(
                name=doc_dict['name'],
                document_type=doc_dict['document_type'],
                entries=entries,
                autor=doc_dict.get('autor', ''),
                rev_tecnica=doc_dict.get('rev_tecnica', ''),
                rev_gerencia=doc_dict.get('rev_gerencia', ''),
                file_paths=file_paths,
                project_phase=doc_dict.get('project_phase', 'Implantación'),
                associated_dwg=doc_dict.get('associated_dwg', '')
            )

            # Set db_id separately to avoid alias issues
            document.db_id = doc_dict['id']

            # Set database manager for future operations
            document.db_manager = db_manager
            document.user_name = user_name

            return document
            
        except Exception as e:
            print(f"Error loading document {name}: {e}")
            return None

    @classmethod
    def load_all_from_database(cls, db_manager, doc_type: str, user_name: str) -> List['SQLiteDocument']:
        """
        Load all documents of a specific type from database.
        This replaces loading from JSON manifest files.
        """
        try:
            documents_data = db_manager.get_documents(doc_type)
            documents = []
            
            for doc_data in documents_data:
                # Convert entries
                entries = []
                for entry_data in doc_data['entries']:
                    entries.append(DocumentEntry(**entry_data))
                
                # Parse file_paths from JSON (handle missing column gracefully)
                import json
                file_paths = []
                try:
                    file_paths_str = doc_data.get('file_paths', '[]')
                    if file_paths_str:
                        file_paths = json.loads(file_paths_str)
                    else:
                        file_paths = []
                except (json.JSONDecodeError, TypeError, KeyError):
                    # Handle cases where file_paths column doesn't exist or has invalid data
                    file_paths = []
                
                # Create document
                document = cls(
                    name=doc_data['name'],
                    document_type=doc_data['document_type'],
                    entries=entries,
                    autor=doc_data.get('autor', ''),
                    rev_tecnica=doc_data.get('rev_tecnica', ''),
                    rev_gerencia=doc_data.get('rev_gerencia', ''),
                    file_paths=file_paths,
                    project_phase=doc_data.get('project_phase', 'Implantación'),
                    associated_dwg=doc_data.get('associated_dwg', '')
                )

                # Set db_id separately to avoid alias issues
                document.db_id = doc_data['id']

                # Set database manager for future operations
                document.db_manager = db_manager
                document.user_name = user_name

                documents.append(document)
            
            return documents
            
        except Exception as e:
            print(f"Error loading documents for {doc_type}: {e}")
            return []

    @classmethod
    def create_new(cls, name: str, doc_type: str, db_manager, user_name: str) -> 'SQLiteDocument':
        """
        Create a new document that will be saved to SQLite.
        This replaces creating new Document objects that save to JSON.
        """
        document = cls(
            name=name,
            document_type=doc_type,
            entries=[]
        )
        
        # Set database manager for future operations
        document.db_manager = db_manager
        document.user_name = user_name
        
        return document


# Compatibility functions to ease migration
def convert_from_old_document(old_document, doc_type: str, db_manager, user_name: str) -> SQLiteDocument:
    """Convert old Document model to SQLiteDocument"""
    new_doc = SQLiteDocument(
        name=old_document.name,
        document_type=doc_type,
        entries=old_document.entries,
        autor=old_document.autor,
        rev_tecnica=old_document.rev_tecnica,
        rev_gerencia=old_document.rev_gerencia
    )
    
    new_doc.db_manager = db_manager
    new_doc.user_name = user_name
    
    return new_doc