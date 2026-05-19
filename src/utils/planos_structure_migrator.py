"""
Planos Structure Migrator
Migrates existing planos from flat structure to organized folder structure.
"""

from pathlib import Path
from typing import Dict, List, Tuple, Optional
import json
import shutil
from datetime import datetime
import logging

from .folder_structure_manager import FolderStructureManager, FileType
from .folder_resolver import FolderResolver
from .project_database_manager import ProjectDatabaseManager


class PlanosStructureMigrator:
    """
    Migrates planos from flat structure to organized folder structure.
    
    Migration Process:
    1. Analyze existing files and their types
    2. Create new folder structure  
    3. Move files to appropriate folders
    4. Update database records with new paths
    5. Preserve file relationships and metadata
    """
    
    def __init__(self, project_path: Path):
        self.project_path = Path(project_path)
        self.planos_path = FolderResolver.resolve_planos(self.project_path)
        self.folder_manager = FolderStructureManager(self.planos_path)
        self.db_manager = ProjectDatabaseManager(self.project_path)
        
        # Set up logging
        self.logger = logging.getLogger(__name__)
        
        # Migration state
        self.migration_report = {
            "started_at": None,
            "completed_at": None,
            "files_processed": 0,
            "files_moved": 0,
            "errors": [],
            "warnings": [],
            "backup_created": False,
            "backup_path": None
        }
    
    def analyze_current_structure(self) -> Dict[str, any]:
        """
        Analyze the current planos structure before migration.
        
        Returns:
            Dictionary with analysis results
        """
        analysis = {
            "total_files": 0,
            "files_by_type": {},
            "needs_migration": False,
            "organized_files": 0,
            "unorganized_files": 0,
            "file_details": []
        }
        
        if not self.planos_path.exists():
            self.logger.warning(f"Planos directory does not exist: {self.planos_path}")
            return analysis
        
        # Get all files in planos directory
        all_files = []
        for file_path in self.planos_path.rglob("*"):
            if file_path.is_file():
                all_files.append(file_path)
        
        analysis["total_files"] = len(all_files)
        
        # Categorize files by type
        for file_path in all_files:
            file_type = self.folder_manager.detect_file_type(file_path)
            
            if file_type:
                type_name = file_type.value
                if type_name not in analysis["files_by_type"]:
                    analysis["files_by_type"][type_name] = 0
                analysis["files_by_type"][type_name] += 1
                
                # Check if file is already organized
                if self.folder_manager.is_file_in_organized_structure(file_path):
                    analysis["organized_files"] += 1
                else:
                    analysis["unorganized_files"] += 1
                    
                analysis["file_details"].append({
                    "path": str(file_path),
                    "type": type_name,
                    "organized": self.folder_manager.is_file_in_organized_structure(file_path),
                    "size": file_path.stat().st_size if file_path.exists() else 0
                })
        
        # Determine if migration is needed
        analysis["needs_migration"] = analysis["unorganized_files"] > 0
        
        return analysis
    
    def create_backup(self) -> bool:
        """
        Create a backup of the current planos structure before migration.
        
        Returns:
            True if backup was created successfully
        """
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{self.planos_path.name}_backup_{timestamp}"
            backup_path = self.project_path / backup_name
            
            if self.planos_path.exists():
                shutil.copytree(self.planos_path, backup_path)
                self.migration_report["backup_created"] = True
                self.migration_report["backup_path"] = str(backup_path)
                self.logger.info(f"✅ Backup created: {backup_path}")
                return True
            else:
                self.logger.warning("No planos directory to backup")
                return True  # Not an error if directory doesn't exist
                
        except Exception as e:
            error_msg = f"Failed to create backup: {e}"
            self.logger.error(f"❌ {error_msg}")
            self.migration_report["errors"].append(error_msg)
            return False
    
    def migrate_files_to_organized_structure(self, create_backup: bool = True) -> bool:
        """
        Migrate all files to the organized folder structure.
        
        Args:
            create_backup: Whether to create a backup before migration
            
        Returns:
            True if migration completed successfully
        """
        try:
            self.migration_report["started_at"] = datetime.now().isoformat()
            
            # Step 1: Analyze current structure
            self.logger.info("🔍 Analyzing current structure...")
            analysis = self.analyze_current_structure()
            
            if not analysis["needs_migration"]:
                self.logger.info("✅ Files already organized, no migration needed")
                return True
            
            self.logger.info(f"📊 Found {analysis['unorganized_files']} files to migrate")
            
            # Step 2: Create backup if requested
            if create_backup:
                self.logger.info("💾 Creating backup...")
                if not self.create_backup():
                    return False
            
            # Step 3: Ensure folder structure exists
            self.logger.info("📁 Creating folder structure...")
            if not self.folder_manager.ensure_folder_structure():
                self.migration_report["errors"].append("Failed to create folder structure")
                return False
            
            # Step 4: Migrate files
            self.logger.info("🚚 Migrating files...")
            for file_detail in analysis["file_details"]:
                if not file_detail["organized"]:
                    success = self._migrate_single_file(file_detail)
                    self.migration_report["files_processed"] += 1
                    if success:
                        self.migration_report["files_moved"] += 1
            
            # Step 5: Update database records
            self.logger.info("🗄️ Updating database records...")
            self._update_database_paths()
            
            self.migration_report["completed_at"] = datetime.now().isoformat()
            self.logger.info(f"✅ Migration completed: {self.migration_report['files_moved']}/{self.migration_report['files_processed']} files migrated")
            
            return True
            
        except Exception as e:
            error_msg = f"Migration failed: {e}"
            self.logger.error(f"❌ {error_msg}")
            self.migration_report["errors"].append(error_msg)
            return False
    
    def _migrate_single_file(self, file_detail: Dict[str, any]) -> bool:
        """
        Migrate a single file to the organized structure.
        
        Args:
            file_detail: File information from analysis
            
        Returns:
            True if file was migrated successfully
        """
        try:
            file_path = Path(file_detail["path"])
            file_type = FileType.from_extension(file_path.suffix)
            
            if not file_type:
                self.migration_report["warnings"].append(f"Unknown file type: {file_path}")
                return False
            
            # Move file to organized structure
            success, new_path, message = self.folder_manager.move_file_to_organized_structure(
                file_path, file_type
            )
            
            if success:
                self.logger.debug(f"✅ {file_path.name} → {new_path}")
                return True
            else:
                self.migration_report["errors"].append(f"Failed to move {file_path.name}: {message}")
                return False
                
        except Exception as e:
            error_msg = f"Error migrating {file_detail['path']}: {e}"
            self.migration_report["errors"].append(error_msg)
            self.logger.error(f"❌ {error_msg}")
            return False
    
    def _update_database_paths(self) -> None:
        """
        Update database records to reflect new file paths.
        """
        try:
            # Get all planos documents from database
            with self.db_manager.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT id, name, file_paths FROM documents WHERE document_type = 'planos'"
                )
                documents = cursor.fetchall()
                
                for doc_id, doc_name, file_paths_json in documents:
                    # Parse existing file paths
                    try:
                        file_paths = json.loads(file_paths_json) if file_paths_json else []
                    except json.JSONDecodeError:
                        file_paths = []
                    
                    # Update file paths to new locations
                    updated_paths = []
                    file_types_found = set()
                    
                    for old_path in file_paths:
                        old_path_obj = Path(old_path)
                        file_type = self.folder_manager.detect_file_type(old_path_obj)
                        
                        if file_type:
                            # Find new organized path
                            new_path = self.folder_manager.get_organized_file_path(
                                old_path_obj.name, file_type
                            )
                            if new_path.exists():
                                updated_paths.append(str(new_path))
                                file_types_found.add(file_type.value)
                    
                    # Update database record
                    primary_file_type = list(file_types_found)[0] if file_types_found else ""
                    folder_path = str(self.folder_manager.get_folder_path(
                        FileType.from_extension(f".{primary_file_type}")
                    )) if primary_file_type else ""
                    
                    conn.execute(
                        """
                        UPDATE documents 
                        SET file_paths = ?, file_type = ?, folder_path = ?, updated_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (json.dumps(updated_paths), primary_file_type, folder_path, doc_id)
                    )
                
                conn.commit()
                self.logger.info(f"✅ Updated {len(documents)} database records")
                
        except Exception as e:
            error_msg = f"Failed to update database paths: {e}"
            self.logger.error(f"❌ {error_msg}")
            self.migration_report["errors"].append(error_msg)

    def validate_migration(self) -> Dict[str, any]:
        """
        Validate the migration results.
        
        Returns:
            Dictionary with validation results
        """
        validation = {
            "structure_valid": False,
            "files_accessible": 0,
            "files_inaccessible": 0,
            "database_consistent": False,
            "issues": []
        }
        
        try:
            # Validate folder structure
            structure_report = self.folder_manager.validate_structure()
            validation["structure_valid"] = structure_report["structure_exists"]
            
            if not validation["structure_valid"]:
                validation["issues"].append("Folder structure is not valid")
            
            # Check file accessibility
            files_by_type = self.folder_manager.get_existing_files_by_type()
            for file_type, files in files_by_type.items():
                for file_path in files:
                    if file_path.exists() and file_path.is_file():
                        validation["files_accessible"] += 1
                    else:
                        validation["files_inaccessible"] += 1
                        validation["issues"].append(f"File not accessible: {file_path}")
            
            # Validate database consistency
            with self.db_manager.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT name, file_paths FROM documents WHERE document_type = 'planos'"
                )
                for doc_name, file_paths_json in cursor.fetchall():
                    try:
                        file_paths = json.loads(file_paths_json) if file_paths_json else []
                        for file_path in file_paths:
                            if not Path(file_path).exists():
                                validation["issues"].append(
                                    f"Database references missing file: {file_path}"
                                )
                    except json.JSONDecodeError:
                        validation["issues"].append(
                            f"Invalid file_paths JSON for document: {doc_name}"
                        )
            
            validation["database_consistent"] = len([
                issue for issue in validation["issues"] 
                if "Database" in issue
            ]) == 0
            
        except Exception as e:
            validation["issues"].append(f"Validation error: {e}")
        
        return validation
    
    def get_migration_report(self) -> Dict[str, any]:
        """
        Get the complete migration report.
        
        Returns:
            Dictionary with migration results and statistics
        """
        return self.migration_report.copy()
    
    def rollback_migration(self) -> bool:
        """
        Rollback migration using the backup.
        
        Returns:
            True if rollback was successful
        """
        try:
            if not self.migration_report.get("backup_created"):
                self.logger.error("❌ No backup available for rollback")
                return False
            
            backup_path = Path(self.migration_report["backup_path"])
            if not backup_path.exists():
                self.logger.error(f"❌ Backup not found: {backup_path}")
                return False
            
            # Remove current structure
            if self.planos_path.exists():
                shutil.rmtree(self.planos_path)
            
            # Restore from backup
            shutil.copytree(backup_path, self.planos_path)
            
            self.logger.info(f"✅ Rollback completed from {backup_path}")
            return True
            
        except Exception as e:
            error_msg = f"Rollback failed: {e}"
            self.logger.error(f"❌ {error_msg}")
            return False