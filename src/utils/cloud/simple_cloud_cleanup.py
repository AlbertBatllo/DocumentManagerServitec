"""
Simple Cloud Cleanup
Deletes all old versions of a document after uploading a new one.
"""

import re
from typing import List, Optional
from dataclasses import dataclass


@dataclass
class CloudFileInfo:
    """Minimal cloud file representation"""
    name: str
    id: str


def extract_base_document_name(filename: str) -> Optional[str]:
    """
    Extract the base document name from various filename formats.

    Handles:
    - Full format: "01_SITUACION_Y_EMPLAZAMIENTO_v2.0_S1.pdf" -> "01_SITUACION_Y_EMPLAZAMIENTO"
    - With number suffix: "01_SITUACION_v1.0_S1 1.pdf" -> "01_SITUACION"
    - With number suffix: "01_SITUACION_v1.0_S1_2.pdf" -> "01_SITUACION"
    - With parentheses: "01_SITUACION_v1.0_S1 (1).pdf" -> "01_SITUACION"
    - Version only: "01_SITUACION_Y_EMPLAZAMIENTO_v2.0.pdf" -> "01_SITUACION_Y_EMPLAZAMIENTO"
    - Simple format: "01 SITUACION Y EMPLAZAMIENTO.pdf" -> "01 SITUACION Y EMPLAZAMIENTO"

    Returns: Base document name or None if cannot parse
    """
    if not filename:
        return None

    # Remove extension
    name_without_ext = filename.rsplit('.', 1)[0] if '.' in filename else filename

    # Pattern 1: Full format with version, state, and optional number suffix
    # Examples:
    #   01_SITUACION_v2.0_S1 -> base: 01_SITUACION
    #   01_SITUACION_v2.0_S1 1 -> base: 01_SITUACION
    #   01_SITUACION_v2.0_S1_2 -> base: 01_SITUACION
    #   01_SITUACION_v2.0_S1 (1) -> base: 01_SITUACION
    # States: S0, S1, S2, S3, S3A, A, B, D
    # Optional suffix: space/underscore + number, or space + (number)
    full_pattern = r'^(.+?)_v\d+\.?\d*_[SBAD]\d*[A-Z]?(?:[\s_]+\d+|\s+\(\d+\))?$'
    match = re.match(full_pattern, name_without_ext, re.IGNORECASE)
    if match:
        return match.group(1)

    # Pattern 2: Format with version only (no state), with optional number suffix
    version_pattern = r'^(.+?)_v\d+\.?\d*(?:[\s_]+\d+|\s+\(\d+\))?$'
    match = re.match(version_pattern, name_without_ext, re.IGNORECASE)
    if match:
        return match.group(1)

    # Pattern 3: Simple name (no version/state)
    # Just return the name without extension
    return name_without_ext


def normalize_for_comparison(name: str) -> str:
    """
    Normalize document name for comparison.
    Converts spaces to underscores and lowercases.

    "01 SITUACION Y EMPLAZAMIENTO" -> "01_situacion_y_emplazamiento"
    """
    if not name:
        return ""
    return name.replace(' ', '_').lower()


def find_files_to_delete(
    uploaded_filenames: List[str],
    cloud_files: List[CloudFileInfo]
) -> List[CloudFileInfo]:
    """
    Find all cloud files that should be deleted after uploading new files.

    Args:
        uploaded_filenames: List of filenames that were just uploaded
        cloud_files: List of files currently in the cloud folder

    Returns:
        List of files to delete (matching base name but NOT in uploaded list)
    """
    if not uploaded_filenames:
        return []

    # Extract base name from first uploaded file (all should have same base)
    uploaded_base = extract_base_document_name(uploaded_filenames[0])
    if not uploaded_base:
        print(f"[SimpleCleanup] Could not extract base name from: {uploaded_filenames[0]}")
        return []

    uploaded_base_normalized = normalize_for_comparison(uploaded_base)

    # Create set of uploaded filenames for fast lookup
    uploaded_set = set(uploaded_filenames)

    files_to_delete = []

    for cloud_file in cloud_files:
        # Skip if it's one of the files we just uploaded
        if cloud_file.name in uploaded_set:
            continue

        # Extract base name from cloud file
        cloud_base = extract_base_document_name(cloud_file.name)
        if not cloud_base:
            continue

        cloud_base_normalized = normalize_for_comparison(cloud_base)

        # Delete if same base name but not in our upload list
        if cloud_base_normalized == uploaded_base_normalized:
            files_to_delete.append(cloud_file)
            print(f"[SimpleCleanup] Will delete old version: {cloud_file.name}")

    return files_to_delete


class SimpleCloudCleanup:
    """Simplified cloud cleanup that deletes all old versions after upload"""

    def __init__(self, cloud_config):
        self.cloud_config = cloud_config

    def cleanup_after_upload(
        self,
        uploaded_filenames: List[str],
        cloud_service: str  # "sharepoint" or "google_drive"
    ) -> dict:
        """
        Clean up old versions after a successful upload.

        Args:
            uploaded_filenames: List of filenames that were just uploaded
                               (can also be a single string for backwards compatibility)
            cloud_service: Which cloud service to clean up

        Returns:
            dict with cleanup results
        """
        # Handle backwards compatibility - accept single string
        if isinstance(uploaded_filenames, str):
            uploaded_filenames = [uploaded_filenames]

        try:
            # Get files from cloud
            if cloud_service == "sharepoint":
                cloud_files = self._get_sharepoint_files()
                delete_fn = self._delete_sharepoint_file
            elif cloud_service == "google_drive":
                cloud_files = self._get_drive_files()
                delete_fn = self._delete_drive_file
            else:
                return {"error": f"Unknown cloud service: {cloud_service}"}

            if not cloud_files:
                return {"message": "No files found in cloud", "deleted": 0}

            # Find files to delete (excludes all uploaded files)
            files_to_delete = find_files_to_delete(uploaded_filenames, cloud_files)

            if not files_to_delete:
                return {"message": "No old versions to delete", "deleted": 0}

            # Delete old versions
            deleted_count = 0
            failed_count = 0
            deleted_names = []

            for file_info in files_to_delete:
                print(f"[SimpleCleanup] Deleting: {file_info.name}")
                if delete_fn(file_info.id):
                    deleted_count += 1
                    deleted_names.append(file_info.name)
                else:
                    failed_count += 1

            return {
                "success": True,
                "deleted": deleted_count,
                "failed": failed_count,
                "deleted_files": deleted_names
            }

        except Exception as e:
            print(f"[SimpleCleanup] Error during cleanup: {e}")
            return {"error": f"Cleanup failed: {e}"}

    def _get_sharepoint_files(self) -> List[CloudFileInfo]:
        """Get list of files from SharePoint"""
        try:
            from .sharepoint_upload import SharePointUploader
            uploader = SharePointUploader(self.cloud_config)
            config = self.cloud_config.get_sharepoint_config()
            folder_path = config.get("folder_path", "")

            raw_files = uploader.list_files(folder_path)
            return [CloudFileInfo(name=f['name'], id=f['id']) for f in raw_files]
        except Exception as e:
            print(f"[SimpleCleanup] Error listing SharePoint files: {e}")
            return []

    def _get_drive_files(self) -> List[CloudFileInfo]:
        """Get list of files from Google Drive"""
        try:
            from .google_drive_upload import GoogleDriveUploader
            uploader = GoogleDriveUploader(self.cloud_config)
            config = self.cloud_config.get_google_drive_config()
            folder_id = config.get("folder_id")

            raw_files = uploader.list_files_in_folder(folder_id)
            return [CloudFileInfo(name=f['name'], id=f['id']) for f in raw_files]
        except Exception as e:
            print(f"[SimpleCleanup] Error listing Google Drive files: {e}")
            return []

    def _delete_sharepoint_file(self, file_id: str) -> bool:
        """Delete a file from SharePoint"""
        try:
            from .sharepoint_upload import SharePointUploader
            uploader = SharePointUploader(self.cloud_config)
            return uploader.delete_file(file_id)
        except Exception as e:
            print(f"[SimpleCleanup] Error deleting SharePoint file: {e}")
            return False

    def _delete_drive_file(self, file_id: str) -> bool:
        """Delete a file from Google Drive"""
        try:
            from .google_drive_upload import GoogleDriveUploader
            uploader = GoogleDriveUploader(self.cloud_config)
            return uploader.delete_file(file_id)
        except Exception as e:
            print(f"[SimpleCleanup] Error deleting Google Drive file: {e}")
            return False
