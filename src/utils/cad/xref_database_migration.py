"""
Database Migration for XREF Support

This module handles migrating the existing documents-based database schema
to support XREF functionality properly, maintaining backward compatibility.
"""

import sqlite3
import logging
import json
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class XrefDatabaseMigration:
    """Handle database schema migration for XREF support."""
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.migration_version = "1.0.0"
    
    def migrate_database(self) -> bool:
        """
        Migrate database to support XREF functionality.
        
        Adds XREF columns to documents table and creates compatibility layer.
        """
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                # Check current schema version
                current_version = self._get_schema_version(conn)
                logger.info(f"Current database schema version: {current_version}")
                
                if current_version >= self.migration_version:
                    logger.info("Database already migrated")
                    return True
                
                # Perform migration steps
                logger.info("Starting XREF database migration...")
                
                # Step 1: Add XREF columns to documents table
                self._add_xref_columns(conn)
                
                # Step 2: Create compatibility views/triggers
                self._create_compatibility_layer(conn)
                
                # Step 3: Create indices for performance
                self._create_xref_indices(conn)
                
                # Step 4: Update schema version
                self._set_schema_version(conn, self.migration_version)
                
                logger.info("XREF database migration completed successfully")
                return True
                
        except Exception as e:
            logger.error(f"Database migration failed: {e}")
            return False
    
    def _get_schema_version(self, conn: sqlite3.Connection) -> str:
        """Get current schema version from database."""
        try:
            cursor = conn.execute("SELECT version FROM schema_version ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            return row[0] if row else "0.0.0"
        except sqlite3.OperationalError:
            # schema_version table doesn't exist, create it
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version TEXT NOT NULL,
                    migrated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            return "0.0.0"
    
    def _set_schema_version(self, conn: sqlite3.Connection, version: str):
        """Set schema version in database."""
        conn.execute("INSERT INTO schema_version (version) VALUES (?)", (version,))
    
    def _add_xref_columns(self, conn: sqlite3.Connection):
        """Add XREF-specific columns to documents table."""
        logger.info("Adding XREF columns to documents table...")
        
        xref_columns = [
            ("plano_type", "TEXT DEFAULT 'main'"),  # 'main' or 'xref'
            ("xref_references", "TEXT DEFAULT NULL"),  # JSON array of references
            ("xref_processing_status", "TEXT DEFAULT NULL"),  # Processing status
            ("xref_method_used", "TEXT DEFAULT NULL"),  # Which extraction method was used
            ("xref_last_processed", "TIMESTAMP DEFAULT NULL")  # When was it last processed
        ]
        
        for column_name, column_def in xref_columns:
            try:
                conn.execute(f"ALTER TABLE documents ADD COLUMN {column_name} {column_def}")
                logger.info(f"Added column: {column_name}")
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    logger.debug(f"Column {column_name} already exists")
                else:
                    raise
    
    def _create_compatibility_layer(self, conn: sqlite3.Connection):
        """Create views and triggers for backward compatibility."""
        logger.info("Creating compatibility layer...")
        
        # Create 'planos' view that maps to documents with document_type='planos'
        # This ensures XREF manager can work with existing code
        conn.execute("""
            CREATE VIEW IF NOT EXISTS planos AS
            SELECT 
                id,
                name,
                current_version as version,
                current_state as state,
                autor,
                rev_tecnica,
                rev_gerencia,
                created_at,
                updated_at,
                plano_type,
                xref_references,
                xref_processing_status,
                xref_method_used,
                xref_last_processed
            FROM documents 
            WHERE document_type = 'planos'
        """)
        
        # Create trigger to update documents when planos view is updated
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS planos_update_trigger
            INSTEAD OF UPDATE ON planos
            BEGIN
                UPDATE documents SET
                    current_version = NEW.version,
                    current_state = NEW.state,
                    autor = NEW.autor,
                    rev_tecnica = NEW.rev_tecnica,
                    rev_gerencia = NEW.rev_gerencia,
                    updated_at = CURRENT_TIMESTAMP,
                    plano_type = NEW.plano_type,
                    xref_references = NEW.xref_references,
                    xref_processing_status = NEW.xref_processing_status,
                    xref_method_used = NEW.xref_method_used,
                    xref_last_processed = NEW.xref_last_processed
                WHERE id = NEW.id AND document_type = 'planos';
            END
        """)
        
        logger.info("Compatibility layer created successfully")
    
    def _create_xref_indices(self, conn: sqlite3.Connection):
        """Create indices for XREF performance."""
        logger.info("Creating XREF indices...")
        
        indices = [
            "CREATE INDEX IF NOT EXISTS idx_documents_plano_type ON documents(plano_type)",
            "CREATE INDEX IF NOT EXISTS idx_documents_xref_status ON documents(xref_processing_status)",
            "CREATE INDEX IF NOT EXISTS idx_documents_name_type ON documents(name, plano_type)",
            "CREATE INDEX IF NOT EXISTS idx_planos_type ON planos(plano_type)",
            "CREATE INDEX IF NOT EXISTS idx_planos_name_type ON planos(name, plano_type)"
        ]
        
        for index_sql in indices:
            try:
                conn.execute(index_sql)
                logger.debug(f"Created index: {index_sql}")
            except sqlite3.OperationalError as e:
                if "already exists" in str(e).lower():
                    logger.debug("Index already exists")
                else:
                    logger.warning(f"Index creation warning: {e}")
    
    def test_migration(self) -> Dict[str, bool]:
        """Test that migration worked correctly."""
        results = {
            "xref_columns_exist": False,
            "planos_view_works": False,
            "indices_exist": False,
            "schema_version_updated": False
        }
        
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                # Test XREF columns
                cursor = conn.execute("PRAGMA table_info(documents)")
                columns = [row[1] for row in cursor.fetchall()]
                required_columns = ["plano_type", "xref_references", "xref_processing_status"]
                results["xref_columns_exist"] = all(col in columns for col in required_columns)
                
                # Test planos view
                try:
                    conn.execute("SELECT COUNT(*) FROM planos")
                    results["planos_view_works"] = True
                except sqlite3.OperationalError:
                    results["planos_view_works"] = False
                
                # Test indices
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%plano%'")
                indices = cursor.fetchall()
                results["indices_exist"] = len(indices) > 0
                
                # Test schema version
                current_version = self._get_schema_version(conn)
                results["schema_version_updated"] = current_version == self.migration_version
                
        except Exception as e:
            logger.error(f"Migration test failed: {e}")
        
        return results
    
    def rollback_migration(self) -> bool:
        """Rollback migration if needed (for development/testing)."""
        logger.warning("Rolling back XREF migration...")
        
        try:
            with sqlite3.connect(str(self.db_path)) as conn:
                # Drop views and triggers
                conn.execute("DROP VIEW IF EXISTS planos")
                conn.execute("DROP TRIGGER IF EXISTS planos_update_trigger")
                
                # Note: SQLite doesn't support DROP COLUMN, so we can't remove the added columns
                # This is acceptable as the columns are harmless and allow forward compatibility
                logger.warning("Note: XREF columns remain in documents table (SQLite limitation)")
                
                # Update schema version
                self._set_schema_version(conn, "0.0.0")
                
                logger.info("Migration rollback completed")
                return True
                
        except Exception as e:
            logger.error(f"Migration rollback failed: {e}")
            return False


def migrate_project_database(project_path: Path) -> bool:
    """Migrate a project's database to support XREF functionality."""
    # Check new location first, then fallback to old location
    db_path = project_path / ".project_manager" / "documents.db"
    if not db_path.exists():
        # Fallback to old location
        db_path = project_path / "documents.db"

    if not db_path.exists():
        logger.warning(f"Database not found in either location")
        return False
    
    migration = XrefDatabaseMigration(db_path)
    success = migration.migrate_database()
    
    if success:
        # Test the migration
        test_results = migration.test_migration()
        logger.info(f"Migration test results: {test_results}")
        
        if not all(test_results.values()):
            logger.warning("Some migration tests failed")
            return False
    
    return success


def migrate_all_projects(base_path: Path) -> Dict[str, bool]:
    """Migrate all project databases in the base directory."""
    results = {}
    
    for project_dir in base_path.iterdir():
        if project_dir.is_dir() and project_dir.name.startswith(("PRJ-", "PRJ_")):
            logger.info(f"Migrating project: {project_dir.name}")
            results[project_dir.name] = migrate_project_database(project_dir)
    
    return results


if __name__ == "__main__":
    # Test migration with the XREF test project
    test_project = Path("PRJ-XREF_Test_Project")
    
    if test_project.exists():
        print(f"🔄 Migrating test project: {test_project}")
        success = migrate_project_database(test_project)
        print(f"✅ Migration {'successful' if success else 'failed'}")
    else:
        print(f"❌ Test project not found: {test_project}")