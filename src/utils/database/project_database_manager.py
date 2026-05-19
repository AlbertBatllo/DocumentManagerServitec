"""
Simple SQLite database manager for project documents.
Replaces JSON manifest files with SQLite for reliability and concurrent access.
"""

import sqlite3
import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import threading
import sys
import time
from contextlib import contextmanager


class ProjectDatabaseManager:
    """
    Manages SQLite database for a single project.
    Simple, reliable, and focused on replacing JSON manifests.
    
    Architecture Decision: Simplified Approach
    ==========================================
    This implementation uses the same simplified approach for ALL platforms
    (Windows, Mac, Linux) to ensure consistent behavior and eliminate 
    Windows-specific database synchronization issues.
    
    Key Simplifications:
    - Thread-local connections instead of connection pooling
    - Standard SQLite settings (PRAGMA synchronous = FULL) for all platforms
    - Generator-based context managers work reliably across platforms
    - Single error handling strategy through built-in database operations
    
    This approach resolves "problema de sincronización de la base de datos"
    and "document locked by None" errors by using Mac's proven, stable strategy.
    """
    
    def __init__(self, project_path: Path):
        self.project_path = Path(project_path)
        self.pm_folder = self.project_path / ".project_manager"
        self.db_path = self.pm_folder / "documents.db"
        self._local = threading.local()

    def _create_optimized_connection(self) -> sqlite3.Connection:
        """Create a new optimized SQLite connection"""
        timeout = 30.0  # Simplified: Use Mac timeout for all platforms
        
        conn = sqlite3.connect(
            str(self.db_path), 
            timeout=timeout,
            check_same_thread=False
        )
        
        # Configure SQLite for better performance and reduced locking
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")  # 30 second busy timeout
        
        # Simplified: Use same settings for all platforms (Mac settings work fine)
        conn.execute("PRAGMA synchronous = FULL")
        
        conn.row_factory = sqlite3.Row
        
        # Run migrations on every new connection
        self._run_migrations(conn)
        
        return conn

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection - simplified to use Mac approach for all platforms"""
        # Simplified: Use thread-local connections on all platforms (works great on Mac)
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = self._create_optimized_connection()
        return self._local.connection

    def close_connection(self) -> None:
        """Close thread-local database connection"""
        if hasattr(self._local, 'connection') and self._local.connection is not None:
            try:
                self._local.connection.close()
            except Exception as e:
                from utils.error_logger import logger
                logger.warning(f"Failed to close thread-local database connection", {"error": str(e)})
            finally:
                self._local.connection = None


    @contextmanager
    def transaction(self):
        """Context manager for database transactions - simplified to work like Mac on all platforms"""
        conn = self._get_connection()
        try:
            # Start transaction
            conn.execute("BEGIN")
            yield conn
            # Commit if no exceptions
            conn.commit()
        except Exception as e:
            # Rollback on any error
            conn.rollback()
            raise e

    @contextmanager
    def connection(self):
        """Context manager for database connections - simplified Mac approach"""
        conn = self._get_connection()
        yield conn

    def initialize_database(self) -> None:
        """Create database and tables if they don't exist"""
        # Ensure .project_manager folder exists
        self.pm_folder.mkdir(parents=True, exist_ok=True)

        with self.connection() as conn:
            try:
                # Create documents table
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS documents (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        document_type TEXT NOT NULL,
                        name TEXT NOT NULL,
                        current_version TEXT DEFAULT '',
                        current_state TEXT DEFAULT '',
                        autor TEXT DEFAULT '',
                        rev_tecnica TEXT DEFAULT '',
                        rev_gerencia TEXT DEFAULT '',
                        file_paths TEXT DEFAULT '[]',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(document_type, name)
                    )
                """)
                
                # Run database migrations
                self._run_migrations(conn)
                
                # Create document entries table (version history)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS document_entries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        document_id INTEGER NOT NULL,
                        version TEXT NOT NULL,
                        state TEXT NOT NULL,
                        author TEXT NOT NULL,
                        notes TEXT DEFAULT '',
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
                    )
                """)
                
                # Create simple locks table - SIMPLEST POSSIBLE LOCKING
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS document_locks (
                        document_id INTEGER PRIMARY KEY,
                        user_name TEXT NOT NULL,
                        locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TIMESTAMP NOT NULL,
                        FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
                    )
                """)
                
                # Create indexes for performance
                conn.execute("CREATE INDEX IF NOT EXISTS idx_documents_type_name ON documents(document_type, name)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_entries_document_timestamp ON document_entries(document_id, timestamp)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_locks_expires ON document_locks(expires_at)")
                
                conn.commit()
                print(f"✅ Database initialized: {self.db_path}")
                
            except sqlite3.Error as e:
                raise RuntimeError(f"Failed to initialize database {self.db_path}: {e}")

    def _run_migrations(self, conn: sqlite3.Connection) -> None:
        """Run database schema migrations."""
        try:
            # Migration 1: Add file_paths column
            try:
                # Check if file_paths column exists
                cursor = conn.execute("PRAGMA table_info(documents)")
                columns = [row[1] for row in cursor.fetchall()]
                
                if 'file_paths' not in columns:
                    conn.execute("ALTER TABLE documents ADD COLUMN file_paths TEXT DEFAULT '[]'")
                    print("✅ Added file_paths column to documents table")
            except sqlite3.OperationalError as e:
                print(f"Migration warning: {e}")
            
            # Migration 2: Add project_phase column for planos preset system
            try:
                # Check if project_phase column exists
                cursor = conn.execute("PRAGMA table_info(documents)")
                columns = [row[1] for row in cursor.fetchall()]
                
                if 'project_phase' not in columns:
                    conn.execute("ALTER TABLE documents ADD COLUMN project_phase TEXT DEFAULT 'Implantación'")
                    print("✅ Added project_phase column to documents table")
            except sqlite3.OperationalError as e:
                print(f"Migration warning: {e}")
            
            # Migration 3: Add file type support for folder organization
            try:
                # Check if file_type and folder_path columns exist
                cursor = conn.execute("PRAGMA table_info(documents)")
                columns = [row[1] for row in cursor.fetchall()]
                
                if 'file_type' not in columns:
                    conn.execute("ALTER TABLE documents ADD COLUMN file_type TEXT DEFAULT ''")
                    print("✅ Added file_type column to documents table")
                    
                if 'folder_path' not in columns:
                    conn.execute("ALTER TABLE documents ADD COLUMN folder_path TEXT DEFAULT ''")
                    print("✅ Added folder_path column to documents table")
            except sqlite3.OperationalError as e:
                print(f"Migration warning: {e}")
            
            # Migration 4: Add file type support to document_entries
            try:
                cursor = conn.execute("PRAGMA table_info(document_entries)")
                columns = [row[1] for row in cursor.fetchall()]
                
                if 'file_path' not in columns:
                    conn.execute("ALTER TABLE document_entries ADD COLUMN file_path TEXT DEFAULT ''")
                    print("✅ Added file_path column to document_entries table")
                    
                if 'file_type' not in columns:
                    conn.execute("ALTER TABLE document_entries ADD COLUMN file_type TEXT DEFAULT ''")
                    print("✅ Added file_type column to document_entries table")
            except sqlite3.OperationalError as e:
                print(f"Migration warning: {e}")
            
            # Migration 5: Add associated_dwg column for DWG file association
            # This allows multiple document entries to reference the same DWG file
            # (one DWG can contain multiple layouts, each tracked as separate entries)
            try:
                cursor = conn.execute("PRAGMA table_info(documents)")
                columns = [row[1] for row in cursor.fetchall()]

                if 'associated_dwg' not in columns:
                    conn.execute("ALTER TABLE documents ADD COLUMN associated_dwg TEXT DEFAULT ''")
                    print("✅ Added associated_dwg column to documents table")
            except sqlite3.OperationalError as e:
                print(f"Migration warning: {e}")

            # Future migrations can be added here
            conn.commit()
            
        except sqlite3.Error as e:
            print(f"Migration error: {e}")
            # Don't fail initialization for migration errors
            pass

    def migrate_from_json(self) -> bool:
        """
        Migrate existing manifest.json files to SQLite.
        Returns True if migration occurred, False if no JSON files found.
        """
        migrated = False
        
        # Look for manifest files in project manager directory
        pm_path = self.project_path / ".project_manager"
        if pm_path.exists():
            # Standard manifest files in .project_manager
            for doc_type in ['planos', 'certificaciones', 'presupuestos']:
                manifest_path = pm_path / doc_type / "manifest.json"
                if manifest_path.exists():
                    print(f"Migrating {doc_type} from {manifest_path}")
                    # Map presupuestos to licitaciones for consistency
                    db_doc_type = 'licitaciones' if doc_type == 'presupuestos' else doc_type
                    self._migrate_document_type(manifest_path, db_doc_type)
                    migrated = True
        
        # Also check for root-level manifest files (current format)
        # documents_manifest.json for planos
        documents_manifest = self.project_path / "documents_manifest.json"
        if documents_manifest.exists():
            print(f"Migrating planos from {documents_manifest}")
            self._migrate_planos_manifest(documents_manifest)
            migrated = True
            
        # certificaciones_manifest.json in certificaciones folder
        cert_manifest = self.project_path / "04_Certificaciones" / "certificaciones_manifest.json"
        if cert_manifest.exists():
            print(f"Migrating certificaciones from {cert_manifest}")
            self._migrate_certificaciones_manifest(cert_manifest)
            migrated = True
                
        return migrated

    def _migrate_document_type(self, manifest_path: Path, doc_type: str) -> None:
        """Migrate a single manifest.json file to SQLite"""
        try:
            # Read JSON data
            with open(manifest_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            documents_data = data.get('documents', {})
            
            with self.transaction() as conn:
                for doc_name, doc_info in documents_data.items():
                    # Insert document
                    cursor = conn.execute("""
                    INSERT OR REPLACE INTO documents 
                    (document_type, name, current_version, current_state, autor, rev_tecnica, rev_gerencia, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    doc_type,
                    doc_name,
                    doc_info.get('current_version', ''),
                    doc_info.get('current_state', ''),
                    doc_info.get('autor', ''),
                    doc_info.get('rev_tecnica', ''),
                    doc_info.get('rev_gerencia', ''),
                    datetime.now().isoformat()
                ))
                
                    document_id = cursor.lastrowid
                    
                    # Insert document entries (version history)
                    entries = doc_info.get('entries', [])
                    for entry in entries:
                        conn.execute("""
                            INSERT INTO document_entries 
                            (document_id, version, state, author, notes, timestamp)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (
                            document_id,
                            entry.get('version', ''),
                            entry.get('state', ''),
                            entry.get('author', ''),
                            entry.get('notes', ''),
                            entry.get('timestamp', datetime.now().isoformat())
                        ))
                
                print(f"✅ Migrated {len(documents_data)} documents from {doc_type}")
            
            # Archive the JSON file
            archive_path = manifest_path.parent / f"manifest_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            manifest_path.rename(archive_path)
            print(f"📁 Archived JSON to: {archive_path}")
            
        except Exception as e:
            print(f"❌ Error migrating {manifest_path}: {e}")
            raise

    def _migrate_planos_manifest(self, manifest_path: Path) -> None:
        """Migrate documents_manifest.json (planos format) to SQLite"""
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            doc_count = 0
            
            with self.transaction() as conn:
                # This format has documents directly in root, keyed by document ID
                for doc_id, doc_info in data.items():
                    if isinstance(doc_info, dict):  # Skip metadata entries
                        # Use a simpler approach: check if document exists first
                        doc_name = doc_info.get('name', doc_id)
                        
                        # Check if document already exists
                        cursor = conn.execute("""
                            SELECT id FROM documents 
                            WHERE document_type = ? AND name = ?
                        """, ('planos', doc_name))
                        
                        existing_row = cursor.fetchone()
                        
                        if existing_row:
                            # Document exists - update it
                            document_id = existing_row['id']
                            conn.execute("""
                                UPDATE documents 
                                SET autor = ?, rev_tecnica = ?, rev_gerencia = ?, updated_at = ?
                                WHERE id = ?
                            """, ('', '', '', datetime.now().isoformat(), document_id))
                        else:
                            # Document doesn't exist - insert it
                            cursor = conn.execute("""
                                INSERT INTO documents 
                                (document_type, name, current_version, current_state, autor, rev_tecnica, rev_gerencia, updated_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                'planos',
                                doc_name,
                                '', # Will be updated from latest entry
                                '', # Will be updated from latest entry
                                '',
                                '',
                                '',
                                datetime.now().isoformat()
                            ))
                            document_id = cursor.lastrowid
                        
                        # Insert document entries if they don't exist, and track latest
                        entries = doc_info.get('entries', [])
                        latest_entry = None
                        
                        # Check existing entries to avoid duplicates
                        existing_entries_cursor = conn.execute("""
                            SELECT version, state, author, timestamp FROM document_entries 
                            WHERE document_id = ?
                        """, (document_id,))
                        existing_entries = [dict(row) for row in existing_entries_cursor.fetchall()]
                        
                        for entry in entries:
                            entry_timestamp = entry.get('timestamp', datetime.now().isoformat())
                            
                            # Check if this entry already exists
                            entry_exists = any(
                                existing['version'] == entry.get('version', '') and
                                existing['state'] == entry.get('state', '') and  
                                existing['author'] == entry.get('author', '') and
                                existing['timestamp'] == entry_timestamp
                                for existing in existing_entries
                            )
                            
                            if not entry_exists:
                                conn.execute("""
                                    INSERT INTO document_entries 
                                    (document_id, version, state, author, notes, timestamp)
                                    VALUES (?, ?, ?, ?, ?, ?)
                                """, (
                                    document_id,
                                    entry.get('version', ''),
                                    entry.get('state', ''),
                                    entry.get('author', ''),
                                    entry.get('notes', ''),
                                    entry_timestamp
                                ))
                            
                            latest_entry = entry
                        
                        # Update document with latest entry info
                        if latest_entry:
                            conn.execute("""
                                UPDATE documents 
                                SET current_version = ?, current_state = ?
                                WHERE id = ?
                            """, (
                                latest_entry.get('version', ''),
                                latest_entry.get('state', ''),
                                document_id
                            ))
                        
                        doc_count += 1
                
                print(f"✅ Migrated {doc_count} planos documents")
            
            # Archive the JSON file
            archive_path = manifest_path.parent / f"documents_manifest_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            manifest_path.rename(archive_path)
            print(f"📁 Archived JSON to: {archive_path}")
            
        except Exception as e:
            print(f"❌ Error migrating planos manifest {manifest_path}: {e}")
            raise

    def _migrate_certificaciones_manifest(self, manifest_path: Path) -> None:
        """Migrate certificaciones_manifest.json to SQLite"""
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            doc_count = 0
            
            with self.transaction() as conn:
                # Similar format to planos - documents keyed by ID
                for doc_id, doc_info in data.items():
                    if isinstance(doc_info, dict):  # Skip metadata entries
                        # Insert document
                        cursor = conn.execute("""
                            INSERT OR REPLACE INTO documents 
                            (document_type, name, current_version, current_state, autor, rev_tecnica, rev_gerencia, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            'certificaciones',
                            doc_info.get('name', doc_id),
                            '', # Will be updated from latest entry
                            '', # Will be updated from latest entry  
                            '',
                            '',
                            '',
                            datetime.now().isoformat()
                        ))
                        
                        document_id = cursor.lastrowid
                        if cursor.rowcount == 0:  # Was an update
                            cursor = conn.execute("SELECT id FROM documents WHERE document_type = ? AND name = ?", 
                                                ('certificaciones', doc_info.get('name', doc_id)))
                            document_id = cursor.fetchone()['id']
                        
                        # Insert document entries
                        entries = doc_info.get('entries', [])
                        latest_entry = None
                        
                        for entry in entries:
                            conn.execute("""
                                INSERT INTO document_entries 
                                (document_id, version, state, author, notes, timestamp)
                                VALUES (?, ?, ?, ?, ?, ?)
                            """, (
                                document_id,
                                entry.get('version', ''),
                                entry.get('state', ''),
                                entry.get('author', ''),
                                entry.get('notes', ''),
                                entry.get('timestamp', datetime.now().isoformat())
                            ))
                            latest_entry = entry
                        
                        # Update document with latest entry info
                        if latest_entry:
                            conn.execute("""
                                UPDATE documents 
                                SET current_version = ?, current_state = ?
                                WHERE id = ?
                            """, (
                                latest_entry.get('version', ''),
                                latest_entry.get('state', ''),
                                document_id
                            ))
                        
                        doc_count += 1
                
                print(f"✅ Migrated {doc_count} certificaciones documents")
            
            # Archive the JSON file
            archive_path = manifest_path.parent / f"certificaciones_manifest_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            manifest_path.rename(archive_path)
            print(f"📁 Archived JSON to: {archive_path}")
            
        except Exception as e:
            print(f"❌ Error migrating certificaciones manifest {manifest_path}: {e}")
            raise

    def get_documents(self, doc_type: str) -> List[Dict[str, Any]]:
        """Get all documents of a specific type"""
        try:
            with self.connection() as conn:
                cursor = conn.execute("""
                    SELECT * FROM documents 
                    WHERE document_type = ?
                    ORDER BY name
                """, (doc_type,))
                
                documents = []
                for row in cursor.fetchall():
                    doc_dict = dict(row)
                    # Get entries for this document
                    entries_cursor = conn.execute("""
                        SELECT version, state, author, notes, timestamp
                        FROM document_entries 
                        WHERE document_id = ?
                        ORDER BY timestamp
                    """, (doc_dict['id'],))
                    
                    doc_dict['entries'] = [dict(entry_row) for entry_row in entries_cursor.fetchall()]
                    documents.append(doc_dict)
                    
                return documents
                
        except sqlite3.Error as e:
            raise RuntimeError(f"Failed to get documents for {doc_type}: {e}")

    def save_document(self, doc_type: str, name: str, document_data: Dict[str, Any], user_name: str) -> int:
        """
        Save document with simple locking.
        Returns document_id.
        """
        # INSERT OR IGNORE + UPDATE preserves the existing row id (avoiding
        # INSERT OR REPLACE's DELETE+INSERT cycle that cascade-deletes
        # document_entries/document_locks and triggers FK failures) while
        # working with any UNIQUE constraint variant (UNIQUE(name) or
        # UNIQUE(document_type, name)).
        try:
            with self.transaction() as conn:
                try:
                    conn.execute("""
                        INSERT OR IGNORE INTO documents
                        (document_type, name, current_version, current_state, autor, rev_tecnica, rev_gerencia, file_paths, project_phase, associated_dwg, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        doc_type,
                        name,
                        document_data.get('current_version', ''),
                        document_data.get('current_state', ''),
                        document_data.get('autor', ''),
                        document_data.get('rev_tecnica', ''),
                        document_data.get('rev_gerencia', ''),
                        json.dumps(document_data.get('file_paths', [])),
                        document_data.get('project_phase', 'Implantación'),
                        document_data.get('associated_dwg', ''),
                        datetime.now().isoformat()
                    ))
                    conn.execute("""
                        UPDATE documents SET
                            current_version = ?,
                            current_state = ?,
                            autor = ?,
                            rev_tecnica = ?,
                            rev_gerencia = ?,
                            file_paths = ?,
                            project_phase = ?,
                            associated_dwg = ?,
                            updated_at = ?
                        WHERE document_type = ? AND name = ?
                    """, (
                        document_data.get('current_version', ''),
                        document_data.get('current_state', ''),
                        document_data.get('autor', ''),
                        document_data.get('rev_tecnica', ''),
                        document_data.get('rev_gerencia', ''),
                        json.dumps(document_data.get('file_paths', [])),
                        document_data.get('project_phase', 'Implantación'),
                        document_data.get('associated_dwg', ''),
                        datetime.now().isoformat(),
                        doc_type,
                        name,
                    ))
                except sqlite3.OperationalError as e:
                    if "no column named" in str(e):
                        # Fallback for databases without newer columns
                        conn.execute("""
                            INSERT OR IGNORE INTO documents
                            (document_type, name, current_version, current_state, autor, rev_tecnica, rev_gerencia, updated_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            doc_type,
                            name,
                            document_data.get('current_version', ''),
                            document_data.get('current_state', ''),
                            document_data.get('autor', ''),
                            document_data.get('rev_tecnica', ''),
                            document_data.get('rev_gerencia', ''),
                            datetime.now().isoformat()
                        ))
                        conn.execute("""
                            UPDATE documents SET
                                current_version = ?,
                                current_state = ?,
                                autor = ?,
                                rev_tecnica = ?,
                                rev_gerencia = ?,
                                updated_at = ?
                            WHERE document_type = ? AND name = ?
                        """, (
                            document_data.get('current_version', ''),
                            document_data.get('current_state', ''),
                            document_data.get('autor', ''),
                            document_data.get('rev_tecnica', ''),
                            document_data.get('rev_gerencia', ''),
                            datetime.now().isoformat(),
                            doc_type,
                            name,
                        ))
                    else:
                        raise e

                cursor = conn.execute(
                    "SELECT id FROM documents WHERE document_type = ? AND name = ?",
                    (doc_type, name)
                )
                row = cursor.fetchone()
                return row['id'] if row else None

        except sqlite3.Error as e:
            from utils.error_logger import logger
            from utils.user_notifications import notify_user_of_database_error

            logger.log_database_error(f"save_document: {doc_type}/{name}", e, None)
            notify_user_of_database_error(
                f"guardar documento {name}",
                f"No se pudo guardar el documento '{name}'. Verifica que no haya problemas de permisos o espacio en disco."
            )
            raise RuntimeError(f"Failed to save document {name}: {e}")
    
    def _save_document_with_connection(self, conn, doc_type: str, name: str, document_data: Dict[str, Any], user_name: str) -> int:
        """
        Save document using an existing connection (for use within transactions).
        Returns document_id.
        """
        # INSERT OR IGNORE + UPDATE preserves the existing row id; avoids cascading delete of children.
        try:
            conn.execute("""
                INSERT OR IGNORE INTO documents
                (document_type, name, current_version, current_state, autor, rev_tecnica, rev_gerencia, file_paths, project_phase, associated_dwg, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                doc_type,
                name,
                document_data.get('current_version', ''),
                document_data.get('current_state', ''),
                document_data.get('autor', ''),
                document_data.get('rev_tecnica', ''),
                document_data.get('rev_gerencia', ''),
                json.dumps(document_data.get('file_paths', [])),
                document_data.get('project_phase', 'Implantación'),
                document_data.get('associated_dwg', ''),
                datetime.now().isoformat()
            ))
            conn.execute("""
                UPDATE documents SET
                    current_version = ?,
                    current_state = ?,
                    autor = ?,
                    rev_tecnica = ?,
                    rev_gerencia = ?,
                    file_paths = ?,
                    project_phase = ?,
                    associated_dwg = ?,
                    updated_at = ?
                WHERE document_type = ? AND name = ?
            """, (
                document_data.get('current_version', ''),
                document_data.get('current_state', ''),
                document_data.get('autor', ''),
                document_data.get('rev_tecnica', ''),
                document_data.get('rev_gerencia', ''),
                json.dumps(document_data.get('file_paths', [])),
                document_data.get('project_phase', 'Implantación'),
                document_data.get('associated_dwg', ''),
                datetime.now().isoformat(),
                doc_type,
                name,
            ))
        except sqlite3.OperationalError as e:
            if "no column named" in str(e):
                conn.execute("""
                    INSERT OR IGNORE INTO documents
                    (document_type, name, current_version, current_state, autor, rev_tecnica, rev_gerencia, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    doc_type,
                    name,
                    document_data.get('current_version', ''),
                    document_data.get('current_state', ''),
                    document_data.get('autor', ''),
                    document_data.get('rev_tecnica', ''),
                    document_data.get('rev_gerencia', ''),
                    datetime.now().isoformat()
                ))
                conn.execute("""
                    UPDATE documents SET
                        current_version = ?,
                        current_state = ?,
                        autor = ?,
                        rev_tecnica = ?,
                        rev_gerencia = ?,
                        updated_at = ?
                    WHERE document_type = ? AND name = ?
                """, (
                    document_data.get('current_version', ''),
                    document_data.get('current_state', ''),
                    document_data.get('autor', ''),
                    document_data.get('rev_tecnica', ''),
                    document_data.get('rev_gerencia', ''),
                    datetime.now().isoformat(),
                    doc_type,
                    name,
                ))
            else:
                raise e

        cursor = conn.execute(
            "SELECT id FROM documents WHERE document_type = ? AND name = ?",
            (doc_type, name)
        )
        row = cursor.fetchone()
        return row['id'] if row else None

    def _add_document_entry_with_connection(self, conn, document_id: int, entry_data: Dict[str, Any]) -> None:
        """Add a new entry to document version history using existing connection"""
        conn.execute("""
            INSERT INTO document_entries 
            (document_id, version, state, author, notes, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            document_id,
            entry_data.get('version', ''),
            entry_data.get('state', ''),
            entry_data.get('author', ''),
            entry_data.get('notes', ''),
            entry_data.get('timestamp', datetime.now().isoformat())
        ))

    def add_document_entry(self, document_id: int, entry_data: Dict[str, Any]) -> None:
        """Add a new entry to document version history"""
        try:
            with self.transaction() as conn:
                conn.execute("""
                    INSERT INTO document_entries 
                    (document_id, version, state, author, notes, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    document_id,
                    entry_data.get('version', ''),
                    entry_data.get('state', ''),
                    entry_data.get('author', ''),
                    entry_data.get('notes', ''),
                    entry_data.get('timestamp', datetime.now().isoformat())
                ))
            
        except sqlite3.Error as e:
            # Get more details about the error
            try:
                with self.connection() as conn:
                    check_cursor = conn.execute("SELECT id, name FROM documents WHERE id = ?", (document_id,))
                    doc_result = check_cursor.fetchone()
                    doc_exists = doc_result is not None
            except Exception:
                doc_exists = "unknown"
            
            from utils.error_logger import logger
            from utils.user_notifications import notify_user_of_database_error
            
            logger.log_database_error(f"add_document_entry to document {document_id}", e, document_id)
            notify_user_of_database_error(
                "agregar entrada al historial del documento",
                "No se pudo guardar la nueva versión del documento. Los cambios pueden perderse."
            )
            raise RuntimeError(f"Failed to add document entry to document {document_id} (exists: {doc_exists}): {e}")

    # SIMPLEST POSSIBLE LOCKING SYSTEM
    def acquire_simple_lock(self, document_id: int, user_name: str, timeout_minutes: int = 30) -> bool:
        """
        Acquire exclusive lock on document. SIMPLE = only one lock per document.
        Returns True if lock acquired, False if already locked by someone else.
        """
        try:
            with self.transaction() as conn:
                # Clean up expired locks first
                conn.execute("""
                    DELETE FROM document_locks 
                    WHERE expires_at < ?
                """, (datetime.now().isoformat(),))
                
                # Try to acquire lock
                expires_at = datetime.now() + timedelta(minutes=timeout_minutes)
                try:
                    conn.execute("""
                        INSERT INTO document_locks (document_id, user_name, expires_at)
                        VALUES (?, ?, ?)
                    """, (document_id, user_name, expires_at.isoformat()))
                    return True
                    
                except sqlite3.IntegrityError:
                    # Lock already exists
                    return False
                
        except sqlite3.Error as e:
            print(f"Error acquiring lock: {e}")
            return False

    def release_simple_lock(self, document_id: int, user_name: str) -> bool:
        """Release lock (only if owned by user)"""
        try:
            with self.transaction() as conn:
                cursor = conn.execute("""
                    DELETE FROM document_locks 
                    WHERE document_id = ? AND user_name = ?
                """, (document_id, user_name))
                return cursor.rowcount > 0
            
        except sqlite3.Error as e:
            print(f"Error releasing lock: {e}")
            return False

    def check_lock_status(self, document_id: int) -> Dict[str, Any]:
        """Check if document is locked and by whom"""
        try:
            with self.connection() as conn:
                # Clean expired locks first
                conn.execute("""
                    DELETE FROM document_locks 
                    WHERE expires_at < ?
                """, (datetime.now().isoformat(),))
                conn.commit()
                
                # Check current lock
                cursor = conn.execute("""
                    SELECT user_name, locked_at, expires_at
                    FROM document_locks 
                    WHERE document_id = ?
                """, (document_id,))
            
            row = cursor.fetchone()
            if row:
                expires_at = datetime.fromisoformat(row['expires_at'])
                return {
                    'is_locked': True,
                    'locked_by': row['user_name'],
                    'locked_at': row['locked_at'],
                    'expires_at': row['expires_at'],
                    'expires_in_minutes': int((expires_at - datetime.now()).total_seconds() / 60)
                }
            else:
                return {
                    'is_locked': False,
                    'locked_by': None,
                    'locked_at': None,
                    'expires_at': None,
                    'expires_in_minutes': 0
                }
                
        except sqlite3.Error as e:
            print(f"Error checking lock status: {e}")
            return {'is_locked': False, 'locked_by': None}

    def cleanup_expired_locks(self) -> int:
        """Clean up all expired locks. Returns number of locks cleaned."""
        try:
            with self.transaction() as conn:
                cursor = conn.execute("""
                    DELETE FROM document_locks 
                    WHERE expires_at < ?
                """, (datetime.now().isoformat(),))
                return cursor.rowcount
            
        except sqlite3.Error as e:
            print(f"Error cleaning expired locks: {e}")
            return 0

    def get_document_id(self, doc_type: str, name: str) -> Optional[int]:
        """Get document ID by type and name"""
        try:
            with self.connection() as conn:
                cursor = conn.execute("""
                    SELECT id FROM documents 
                    WHERE document_type = ? AND name = ?
                """, (doc_type, name))
            
            row = cursor.fetchone()
            return row['id'] if row else None
            
        except sqlite3.Error as e:
            print(f"Error getting document ID: {e}")
            return None

    def delete_document(self, document_id: int) -> bool:
        """Delete a document and all its entries"""
        try:
            with self.transaction() as conn:
                # Delete entries first (foreign key cascade should handle this, but be explicit)
                conn.execute("DELETE FROM document_entries WHERE document_id = ?", (document_id,))
                
                # Delete document
                cursor = conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))
                
                # Return True if document was actually deleted
                return cursor.rowcount > 0
            
        except sqlite3.Error as e:
            from utils.error_logger import logger
            from utils.user_notifications import notify_user_of_database_error
            
            logger.log_database_error(f"delete_document {document_id}", e, document_id)
            notify_user_of_database_error(
                "eliminar documento",
                "No se pudo eliminar el documento de la base de datos. Puede que siga apareciendo en la lista."
            )
            raise RuntimeError(f"Failed to delete document {document_id}: {e}")

    def close(self) -> None:
        """Close database connection"""
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None


def ensure_project_database(project_path: Path) -> ProjectDatabaseManager:
    """
    Ensure project has SQLite database initialized.
    Auto-creates database if missing, auto-migrates from JSON if found.
    Also handles migration from old location (project root) to new location (.project_manager folder).
    This is the main entry point that replaces JSON manifest loading.
    """
    import shutil

    project_path = Path(project_path)
    db_manager = ProjectDatabaseManager(project_path)

    # Check for database in old location (project root) and migrate if needed
    old_db_path = project_path / "documents.db"
    if old_db_path.exists() and not db_manager.db_path.exists():
        print(f"📦 Migrating database from old location to .project_manager folder...")
        # Ensure .project_manager folder exists
        db_manager.pm_folder.mkdir(parents=True, exist_ok=True)
        # Move database to new location
        shutil.move(str(old_db_path), str(db_manager.db_path))
        print(f"✅ Database migrated to: {db_manager.db_path}")

    # Initialize database if it doesn't exist
    if not db_manager.db_path.exists():
        print(f"🔧 Creating database for project: {project_path.name}")
        db_manager.initialize_database()

        # Check for existing manifest files to migrate
        if db_manager.migrate_from_json():
            print(f"📦 Migration completed for: {project_path.name}")
        else:
            print(f"✨ New database created for: {project_path.name}")

    return db_manager