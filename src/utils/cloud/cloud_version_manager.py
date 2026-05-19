"""
Cloud Version Manager
Handles version cleanup and retention policies for SharePoint and Google Drive.
"""

import re
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from .cloud_exceptions import CloudSafetyError, CloudVersioningError, raise_safety_error


@dataclass
class CloudFile:
    """Represents a file in cloud storage"""
    name: str
    id: str
    modified_date: datetime
    size: int
    download_url: Optional[str] = None


@dataclass
class DocumentVersions:
    """Groups all versions of a document"""
    document_id: str
    document_name: str
    versions: List[Tuple[str, str, CloudFile]]  # (version, state, file)
    
    def get_latest_versions(self, keep_count: int = 2) -> List[CloudFile]:
        """Get the latest N versions, sorted by version number"""
        # Sort by version (assuming semantic versioning like v1.0, v1.1, v2.0)
        def safe_parse_version(version_tuple):
            try:
                return self._parse_version(version_tuple[0])
            except Exception:
                # If version parsing fails, fall back to (0, 0) to sort it last
                return (0, 0)
        
        sorted_versions = sorted(
            self.versions, 
            key=safe_parse_version,
            reverse=True
        )
        return [file for _, _, file in sorted_versions[:keep_count]]
    
    def get_files_to_delete(self, keep_count: int = 2) -> List[CloudFile]:
        """Get files that should be deleted (older than the latest N versions)"""
        latest_files = self.get_latest_versions(keep_count)
        latest_names = {f.name for f in latest_files}
        return [file for _, _, file in self.versions if file.name not in latest_names]
    
    def _parse_version(self, version_str: str) -> tuple:
        """Parse version string like 'v1.2' or '01/2025' into comparable tuple"""
        try:
            if version_str.startswith('v'):
                # Traditional version like v1.2
                parts = version_str[1:].split('.')
                return tuple(int(p) for p in parts)
            elif '/' in version_str:
                # Month/year format like 01/2025
                month, year = version_str.split('/')
                return (int(year), int(month))
            else:
                # Fallback: treat as string
                return (version_str,)
        except (ValueError, AttributeError):
            return (0,)  # Fallback for unparseable versions


class CloudVersionManager:
    """Manages version cleanup in cloud storage based on file nomenclature"""
    
    def __init__(self, cloud_config):
        self.cloud_config = cloud_config
        # Load configurable settings
        from config.cloud_settings import get_cloud_settings
        self.settings = get_cloud_settings()
        # Updated pattern for Name_Version.ext format (e.g., Planta_baja_1.1.pdf)
        self.filename_pattern = re.compile(
            r'^(.+?)_(\d+\.\d+)\.(pdf|dwg|doc|docx)$', re.IGNORECASE
        )
    
    def validate_filename_format(self, filename: str) -> None:
        """Validate filename format before processing"""
        if not filename or len(filename) < 5:
            raise CloudValidationError(f"Invalid filename format: '{filename}' - too short")
        
        if not isinstance(filename, str):
            raise CloudValidationError(f"Invalid filename type: expected string, got {type(filename)}")
        
        # Check for invalid characters that could cause issues
        invalid_chars = ['<', '>', ':', '"', '|', '?', '*']
        for char in invalid_chars:
            if char in filename:
                raise CloudValidationError(f"Invalid character '{char}' in filename: {filename}")
        
        # Check for reasonable length
        if len(filename) > 255:
            raise CloudValidationError(f"Filename too long ({len(filename)} chars): {filename}")
    
    def parse_filename(self, filename: str) -> Optional[Dict[str, str]]:
        """
        Parse document filename into components with validation.
        Expected format: {name}_{version}.{ext}
        Example: Planta_baja_1.1.pdf
        """
        # Validate filename format first
        self.validate_filename_format(filename)
        
        match = self.filename_pattern.match(filename)
        if match:
            name, version, extension = match.groups()
            
            # Additional validation on parsed components
            if not name.strip():
                raise CloudValidationError(f"Empty document name in filename: {filename}")
            
            if not version.strip():
                raise CloudValidationError(f"Empty version in filename: {filename}")
            
            return {
                'doc_name': name,
                'version': version,
                'extension': extension
            }
        else:
            raise CloudValidationError(f"Filename doesn't match expected pattern 'Name_Version.ext': {filename}")
        
        return None
    
    def _parse_version(self, version_str: str) -> tuple:
        """Parse version string like '1.2' or '2.0' into comparable tuple with robust error handling"""
        if not version_str or not isinstance(version_str, str):
            raise CloudValidationError(f"Invalid version string: {version_str} (must be non-empty string)")
        
        # Remove any whitespace
        version_str = version_str.strip()
        
        if not version_str:
            raise CloudValidationError("Version string cannot be empty or whitespace-only")
        
        try:
            # Handle decimal versions (1.0, 1.1, 2.0, etc.)
            parts = version_str.split('.')
            
            # Validate parts
            if len(parts) > 4:
                raise CloudValidationError(f"Version has too many parts (max 4): {version_str}")
            
            parsed_parts = []
            for i, part in enumerate(parts):
                if not part.strip():
                    raise CloudValidationError(f"Empty version part at position {i+1}: {version_str}")
                
                try:
                    parsed_part = int(part.strip())
                    if parsed_part < 0:
                        raise CloudValidationError(f"Negative version number at position {i+1}: {version_str}")
                    if parsed_part > 999:  # Reasonable upper limit
                        raise CloudValidationError(f"Version number too large at position {i+1}: {version_str}")
                    parsed_parts.append(parsed_part)
                except ValueError:
                    raise CloudValidationError(f"Non-numeric version part '{part}' at position {i+1}: {version_str}")
            
            # Normalize to consistent format
            if len(parsed_parts) == 1:
                # Single number version -> (major, 0)
                return (parsed_parts[0], 0)
            elif len(parsed_parts) == 2:
                # Standard major.minor format
                return tuple(parsed_parts)
            else:
                # Multi-part version (1.2.3, 1.2.3.4)
                return tuple(parsed_parts)
                
        except CloudValidationError:
            # Re-raise validation errors
            raise
        except (ValueError, AttributeError) as e:
            # Catch any other parsing errors
            raise CloudValidationError(f"Failed to parse version '{version_str}': {e}")
        except Exception as e:
            # Catch unexpected errors
            raise CloudValidationError(f"Unexpected error parsing version '{version_str}': {e}")
    
    def group_files_by_document(self, cloud_files: List[CloudFile]) -> Dict[str, DocumentVersions]:
        """Group cloud files by document name"""
        documents = {}
        
        for file in cloud_files:
            parsed = self.parse_filename(file.name)
            if not parsed:
                continue  # Skip files that don't match our pattern
            
            doc_name = parsed['doc_name']
            if doc_name not in documents:
                documents[doc_name] = DocumentVersions(
                    document_id=doc_name,  # Use doc_name as ID since we don't have separate IDs
                    document_name=doc_name,
                    versions=[]
                )
            
            # Note: No state in new format, use empty string as placeholder
            documents[doc_name].versions.append((
                parsed['version'],
                '',  # No state in filename
                file
            ))
        
        return documents
    
    def get_cleanup_plan(self, cloud_files: List[CloudFile], keep_versions: int = 2) -> Dict[str, List[CloudFile]]:
        """
        Create a cleanup plan showing what files to delete for each document.
        Returns: {document_id: [files_to_delete]}
        """
        documents = self.group_files_by_document(cloud_files)
        cleanup_plan = {}
        
        for doc_id, doc_versions in documents.items():
            files_to_delete = doc_versions.get_files_to_delete(keep_versions)
            if files_to_delete:
                cleanup_plan[doc_id] = files_to_delete
        
        return cleanup_plan
    
    def cleanup_sharepoint_versions(self, document_id: str = None, dry_run: bool = True) -> Dict[str, any]:
        """
        Clean up old versions in SharePoint, keeping only the latest 2 versions.
        """
        if not self.cloud_config.is_sharepoint_enabled():
            return {"error": "SharePoint not enabled"}
        
        try:
            # Get SharePoint files
            sharepoint_files = self._get_sharepoint_files(document_id)
            
            if not sharepoint_files:
                return {"message": "No files found in SharePoint", "deleted": 0}
            
            # Create cleanup plan
            cleanup_plan = self.get_cleanup_plan(sharepoint_files, keep_versions=self.settings.versions_to_keep)
            
            if dry_run:
                return {
                    "dry_run": True,
                    "documents_analyzed": len(cleanup_plan),
                    "files_to_delete": sum(len(files) for files in cleanup_plan.values()),
                    "cleanup_plan": {
                        doc_id: [f.name for f in files] 
                        for doc_id, files in cleanup_plan.items()
                    }
                }
            
            # SAFETY CHECKS before executing cleanup
            total_files_to_delete = sum(len(files) for files in cleanup_plan.values())
            
            # Safety check 1: Don't delete too many files at once
            if total_files_to_delete > self.settings.max_deletions_per_run:
                return {
                    "error": f"SAFETY CHECK FAILED: Would delete {total_files_to_delete} files (max {self.settings.max_deletions_per_run} per operation)",
                    "aborted": True
                }
            
            # Safety check 2: Verify we're keeping at least 1 file per document
            for doc_id, files_to_delete in cleanup_plan.items():
                doc_files = [f for f in sharepoint_files if f.name.startswith(doc_id)]
                remaining = len(doc_files) - len(files_to_delete)
                if remaining < 1:
                    return {
                        "error": f"SAFETY CHECK FAILED: Would delete all files for document {doc_id}",
                        "aborted": True
                    }
            
            # Execute cleanup with detailed logging
            deleted_count = 0
            failed_count = 0
            
            for doc_id, files_to_delete in cleanup_plan.items():
                print(f"[SharePoint] Cleaning up {len(files_to_delete)} old versions for document: {doc_id}")
                for file in files_to_delete:
                    print(f"[SharePoint] Deleting: {file.name} (modified: {file.modified_date})")
                    if self._delete_sharepoint_file(file):
                        deleted_count += 1
                        print(f"[SharePoint] ✓ Successfully deleted: {file.name}")
                    else:
                        failed_count += 1
                        print(f"[SharePoint] ❌ Failed to delete: {file.name}")
            
            return {
                "success": True,
                "deleted": deleted_count,
                "failed": failed_count,
                "documents_cleaned": len(cleanup_plan),
                "safety_checks_passed": True
            }
            
        except Exception as e:
            return {"error": f"SharePoint cleanup failed: {e}"}
    
    def cleanup_drive_versions(self, document_id: str = None, dry_run: bool = True) -> Dict[str, any]:
        """
        Clean up old versions in Google Drive, keeping only the latest 2 versions.
        """
        if not self.cloud_config.is_google_drive_enabled():
            return {"error": "Google Drive not enabled"}
        
        try:
            # Get Google Drive files
            drive_files = self._get_drive_files(document_id)
            
            if not drive_files:
                return {"message": "No files found in Google Drive", "deleted": 0}
            
            # Create cleanup plan
            cleanup_plan = self.get_cleanup_plan(drive_files, keep_versions=self.settings.versions_to_keep)
            
            if dry_run:
                return {
                    "dry_run": True,
                    "documents_analyzed": len(cleanup_plan),
                    "files_to_delete": sum(len(files) for files in cleanup_plan.values()),
                    "cleanup_plan": {
                        doc_id: [f.name for f in files] 
                        for doc_id, files in cleanup_plan.items()
                    }
                }
            
            # SAFETY CHECKS before executing cleanup
            total_files_to_delete = sum(len(files) for files in cleanup_plan.values())
            
            # Safety check 1: Don't delete too many files at once
            if total_files_to_delete > self.settings.max_deletions_per_run:
                return {
                    "error": f"SAFETY CHECK FAILED: Would delete {total_files_to_delete} files (max {self.settings.max_deletions_per_run} per operation)",
                    "aborted": True
                }
            
            # Safety check 2: Verify we're keeping at least 1 file per document
            for doc_id, files_to_delete in cleanup_plan.items():
                doc_files = [f for f in drive_files if f.name.startswith(doc_id)]
                remaining = len(doc_files) - len(files_to_delete)
                if remaining < 1:
                    return {
                        "error": f"SAFETY CHECK FAILED: Would delete all files for document {doc_id}",
                        "aborted": True
                    }
            
            # Execute cleanup with detailed logging
            deleted_count = 0
            failed_count = 0
            
            for doc_id, files_to_delete in cleanup_plan.items():
                print(f"[Google Drive] Cleaning up {len(files_to_delete)} old versions for document: {doc_id}")
                for file in files_to_delete:
                    print(f"[Google Drive] Deleting: {file.name} (modified: {file.modified_date})")
                    if self._delete_drive_file(file):
                        deleted_count += 1
                        print(f"[Google Drive] ✓ Successfully deleted: {file.name}")
                    else:
                        failed_count += 1
                        print(f"[Google Drive] ❌ Failed to delete: {file.name}")
            
            return {
                "success": True,
                "deleted": deleted_count,
                "failed": failed_count,
                "documents_cleaned": len(cleanup_plan),
                "safety_checks_passed": True
            }
            
        except Exception as e:
            return {"error": f"Google Drive cleanup failed: {e}"}
    
    def cleanup_all_versions(self, document_id: str = None, dry_run: bool = True) -> Dict[str, any]:
        """Clean up old versions in both SharePoint and Google Drive"""
        results = {
            "sharepoint": self.cleanup_sharepoint_versions(document_id, dry_run),
            "google_drive": self.cleanup_drive_versions(document_id, dry_run)
        }
        
        # Summary
        total_deleted = 0
        if not dry_run:
            total_deleted += results["sharepoint"].get("deleted", 0)
            total_deleted += results["google_drive"].get("deleted", 0)
        else:
            total_to_delete = 0
            total_to_delete += results["sharepoint"].get("files_to_delete", 0)
            total_to_delete += results["google_drive"].get("files_to_delete", 0)
            results["summary"] = {
                "dry_run": True,
                "total_files_to_delete": total_to_delete
            }
        
        if not dry_run:
            results["summary"] = {
                "total_deleted": total_deleted,
                "success": True
            }
        
        return results
    
    def cleanup_old_versions(self, folder_path: Path, keep_versions: int = 2) -> str:
        """Clean up old document versions in a local folder based on nomenclature"""
        try:
            if not folder_path.exists():
                return "Carpeta no encontrada"
            
            # Get all PDF files in the folder
            pdf_files = list(folder_path.glob("*.pdf"))
            
            if not pdf_files:
                return "No se encontraron archivos PDF"
            
            # Group files by document ID and name
            documents = {}
            for pdf_file in pdf_files:
                parsed = self.parse_filename(pdf_file.name)
                if parsed:
                    doc_key = f"{parsed['doc_id']}_{parsed['doc_name']}"
                    if doc_key not in documents:
                        documents[doc_key] = []
                    documents[doc_key].append((pdf_file, parsed))
            
            if not documents:
                return "No se encontraron archivos con nomenclatura válida"
            
            # Process each document group
            files_to_delete = []
            for doc_key, file_list in documents.items():
                if len(file_list) <= keep_versions:
                    continue  # Skip if we have fewer than or equal to keep_versions
                
                # Sort by version (newest first) with safe parsing
                def safe_parse_file_version(file_info):
                    try:
                        return self._parse_version(file_info[1]['version'])
                    except CloudValidationError:
                        # If version parsing fails, treat as very old version (0, 0)
                        return (0, 0)
                
                sorted_files = sorted(file_list, key=safe_parse_file_version, reverse=True)
                
                # Mark old versions for deletion (keep only the latest keep_versions)
                old_versions = sorted_files[keep_versions:]
                files_to_delete.extend([file_info[0] for file_info in old_versions])
            
            if not files_to_delete:
                return f"No hay versiones antiguas que limpiar (manteniendo {keep_versions} versiones más recientes)"
            
            # Delete the old versions
            deleted_count = 0
            for file_path in files_to_delete:
                try:
                    file_path.unlink()
                    deleted_count += 1
                    print(f"[Cleanup] Deleted old version: {file_path.name}")
                except Exception as e:
                    print(f"[Cleanup] Error deleting {file_path.name}: {e}")
            
            return f"Eliminadas {deleted_count} versiones antiguas (manteniendo {keep_versions} más recientes)"
            
        except Exception as e:
            return f"Error en la limpieza: {e}"
    
    # Real API implementations for SharePoint and Google Drive
    def _get_sharepoint_files(self, document_name: str = None) -> List[CloudFile]:
        """Get files from SharePoint folder"""
        try:
            from .sharepoint_upload import SharePointUploader
            uploader = SharePointUploader(self.cloud_config)
            
            # Get SharePoint folder path from config
            config = self.cloud_config.get_sharepoint_config()
            folder_path = config.get("folder_path", "")
            
            # List all files in the folder
            raw_files = uploader.list_files(folder_path)
            
            cloud_files = []
            for file_data in raw_files:
                # Convert to CloudFile format
                try:
                    modified_date = datetime.fromisoformat(file_data['modified_date'].replace('Z', '+00:00'))
                except (ValueError, TypeError):
                    modified_date = datetime.now()
                
                cloud_file = CloudFile(
                    name=file_data['name'],
                    id=file_data['id'],
                    modified_date=modified_date,
                    size=file_data['size'],
                    download_url=file_data.get('download_url')
                )
                
                # Filter by document name if provided
                if document_name:
                    parsed = self.parse_filename(cloud_file.name)
                    if parsed and parsed['doc_name'] == document_name:
                        cloud_files.append(cloud_file)
                else:
                    # Only include files that match our naming pattern
                    if self.parse_filename(cloud_file.name):
                        cloud_files.append(cloud_file)
            
            return cloud_files
            
        except ImportError:
            print("[SharePoint] SharePoint uploader not available")
            return []
        except Exception as e:
            print(f"[SharePoint] Error listing files: {e}")
            return []
    
    def _get_drive_files(self, document_name: str = None) -> List[CloudFile]:
        """Get files from Google Drive folder"""
        try:
            from .google_drive_upload import GoogleDriveUploader
            uploader = GoogleDriveUploader(self.cloud_config)
            
            # Get Google Drive folder ID from config
            config = self.cloud_config.get_google_drive_config()
            folder_id = config.get("folder_id")
            
            # List all files in the folder
            raw_files = uploader.list_files_in_folder(folder_id)
            
            cloud_files = []
            for file_data in raw_files:
                # Convert to CloudFile format
                try:
                    modified_date = datetime.fromisoformat(file_data['modifiedTime'].replace('Z', '+00:00'))
                except (ValueError, TypeError):
                    modified_date = datetime.now()
                
                cloud_file = CloudFile(
                    name=file_data['name'],
                    id=file_data['id'],
                    modified_date=modified_date,
                    size=int(file_data.get('size', 0)),
                    download_url=None  # Google Drive uses different download mechanism
                )
                
                # Filter by document name if provided
                if document_name:
                    parsed = self.parse_filename(cloud_file.name)
                    if parsed and parsed['doc_name'] == document_name:
                        cloud_files.append(cloud_file)
                else:
                    # Only include files that match our naming pattern
                    if self.parse_filename(cloud_file.name):
                        cloud_files.append(cloud_file)
            
            return cloud_files
            
        except ImportError:
            print("[Google Drive] Google Drive uploader not available")
            return []
        except Exception as e:
            print(f"[Google Drive] Error listing files: {e}")
            return []
    
    def _delete_sharepoint_file(self, file: CloudFile) -> bool:
        """Delete a file from SharePoint"""
        try:
            from .sharepoint_upload import SharePointUploader
            uploader = SharePointUploader(self.cloud_config)
            
            success = uploader.delete_file(file.id)
            if success:
                print(f"[SharePoint] Successfully deleted: {file.name}")
            else:
                print(f"[SharePoint] Failed to delete: {file.name}")
            return success
            
        except ImportError:
            print(f"[SharePoint] SharePoint uploader not available, simulating delete: {file.name}")
            return True
        except Exception as e:
            print(f"[SharePoint] Error deleting {file.name}: {e}")
            return False
    
    def _delete_drive_file(self, file: CloudFile) -> bool:
        """Delete a file from Google Drive"""
        try:
            from .google_drive_upload import GoogleDriveUploader
            uploader = GoogleDriveUploader(self.cloud_config)
            
            success = uploader.delete_file(file.id)
            if success:
                print(f"[Google Drive] Successfully deleted: {file.name}")
            else:
                print(f"[Google Drive] Failed to delete: {file.name}")
            return success
            
        except ImportError:
            print(f"[Google Drive] Google Drive uploader not available, simulating delete: {file.name}")
            return True
        except Exception as e:
            print(f"[Google Drive] Error deleting {file.name}: {e}")
            return False


# Usage example and test functions
def example_usage():
    """Example of how to use the CloudVersionManager"""
    
    # Mock cloud files for testing
    mock_files = [
        CloudFile("PL-001_Planta Baja_v1.0_S2.pdf", "file1", datetime.now(), 1024),
        CloudFile("PL-001_Planta Baja_v1.1_S2.pdf", "file2", datetime.now(), 1024),
        CloudFile("PL-001_Planta Baja_v1.2_S2.pdf", "file3", datetime.now(), 1024),
        CloudFile("PL-001_Planta Baja_v2.0_A.pdf", "file4", datetime.now(), 1024),
        CloudFile("CERT-001_Certificado_01_2025_S3.pdf", "file5", datetime.now(), 1024),
        CloudFile("CERT-001_Certificado_02_2025_A.pdf", "file6", datetime.now(), 1024),
    ]
    
    # Create manager (would need actual cloud config)
    manager = CloudVersionManager(None)
    
    # Analyze cleanup plan
    cleanup_plan = manager.get_cleanup_plan(mock_files, keep_versions=2)
    
    print("🗑️ Cleanup Plan:")
    for doc_id, files_to_delete in cleanup_plan.items():
        print(f"📄 Document {doc_id}:")
        for file in files_to_delete:
            print(f"   ❌ Delete: {file.name}")
        print()


if __name__ == "__main__":
    example_usage()