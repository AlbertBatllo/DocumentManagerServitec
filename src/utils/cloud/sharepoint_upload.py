"""
SharePoint Upload Module
Handles real file uploads to SharePoint using Microsoft Graph API
"""

import os
import json
import requests
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import hashlib


class SharePointUploader:
    """Handles file uploads to SharePoint using Microsoft Graph API"""
    
    GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
    
    def __init__(self, cloud_config):
        self.cloud_config = cloud_config
        self.access_token = None
        # Load configurable chunk size
        from config.cloud_settings import get_cloud_settings
        self.settings = get_cloud_settings()
        # Initialize token refresh manager
        from .token_refresh import TokenRefreshManager
        self.token_manager = TokenRefreshManager(cloud_config)
        self._load_access_token()
    
    def _load_access_token(self):
        """Load the current access token from cloud config"""
        creds = self.cloud_config.get_user_credentials("sharepoint")
        if creds:
            self.access_token = creds.get("access_token")
    
    def _ensure_valid_token(self) -> bool:
        """Ensure we have a valid access token, refresh if needed"""
        try:
            # Check if token is valid, refresh if needed
            if not self.token_manager.is_token_valid("sharepoint"):
                success = self.token_manager.refresh_sharepoint_token()
                if not success:
                    return False
                # Reload the token after refresh
                self._load_access_token()
            return True
        except Exception as e:
            print(f"Error ensuring valid SharePoint token: {e}")
            return False
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for API requests with automatic token refresh"""
        # Ensure token is valid before making request
        if not self._ensure_valid_token():
            raise ValueError("Unable to obtain valid SharePoint access token")
        
        if not self.access_token:
            raise ValueError("No access token available. Please authenticate first.")
        
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json"
        }
    
    def _make_authenticated_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make authenticated request with automatic retry on token expiration"""
        max_retries = 2
        for attempt in range(max_retries):
            try:
                headers = self._get_headers()
                # Merge with any additional headers
                if 'headers' in kwargs:
                    headers.update(kwargs['headers'])
                kwargs['headers'] = headers
                
                response = requests.request(method, url, **kwargs)
                
                # If we get 401 Unauthorized, try refreshing token once
                if response.status_code == 401 and attempt < max_retries - 1:
                    print(f"SharePoint request failed with 401, attempting token refresh (attempt {attempt + 1}/{max_retries})")
                    # Force token refresh
                    success = self.token_manager.refresh_sharepoint_token()
                    if success:
                        self._load_access_token()
                        continue  # Retry with new token
                    else:
                        print("Failed to refresh SharePoint token")
                        break
                
                return response
                
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"SharePoint request error, retrying: {e}")
                    continue
                else:
                    raise
        
        # If we get here, all retries failed
        raise ValueError("All SharePoint request attempts failed")
    
    def _get_site_id(self, site_url: str) -> Optional[str]:
        """Get SharePoint site ID from site URL"""
        try:
            # Parse site URL to get hostname and site path
            # Example: https://company.sharepoint.com/sites/ProjectDocs
            from urllib.parse import urlparse
            parsed = urlparse(site_url)
            hostname = parsed.hostname
            site_path = parsed.path.replace('/sites/', '')
            
            # Get site ID using Graph API with automatic retry
            url = f"{self.GRAPH_API_BASE}/sites/{hostname}:/sites/{site_path}"
            response = self._make_authenticated_request('GET', url)
            
            if response.status_code == 200:
                return response.json().get("id")
            else:
                print(f"Failed to get site ID: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            print(f"Error getting site ID: {e}")
            return None
    
    def _get_drive_id(self, site_id: str) -> Optional[str]:
        """Get the default document library drive ID for a site"""
        try:
            url = f"{self.GRAPH_API_BASE}/sites/{site_id}/drive"
            response = self._make_authenticated_request('GET', url)
            
            if response.status_code == 200:
                return response.json().get("id")
            else:
                print(f"Failed to get drive ID: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"Error getting drive ID: {e}")
            return None
    
    def create_folder_if_needed(self, folder_path: str) -> bool:
        """Create folder structure in SharePoint if it doesn't exist"""
        try:
            config = self.cloud_config.get_sharepoint_config()
            site_url = config.get("site_url")
            
            if not site_url:
                return False
            
            site_id = self._get_site_id(site_url)
            if not site_id:
                return False
            
            drive_id = self._get_drive_id(site_id)
            if not drive_id:
                return False
            
            # Create folder structure
            folder_parts = folder_path.strip('/').split('/')
            current_path = ""
            
            for folder_name in folder_parts:
                current_path = f"{current_path}/{folder_name}" if current_path else folder_name
                
                # Check if folder exists
                check_url = f"{self.GRAPH_API_BASE}/drives/{drive_id}/root:/{current_path}"
                check_response = self._make_authenticated_request('GET', check_url)
                
                if check_response.status_code == 404:
                    # Folder doesn't exist, create it
                    parent_path = "/".join(current_path.split("/")[:-1])
                    parent_url = f"{self.GRAPH_API_BASE}/drives/{drive_id}/root:/{parent_path}:/children" if parent_path else f"{self.GRAPH_API_BASE}/drives/{drive_id}/root/children"
                    
                    folder_data = {
                        "name": folder_name,
                        "folder": {},
                        "@microsoft.graph.conflictBehavior": "rename"
                    }
                    
                    create_response = self._make_authenticated_request(
                        'POST', parent_url,
                        headers={"Content-Type": "application/json"},
                        json=folder_data
                    )
                    
                    if create_response.status_code not in [200, 201]:
                        print(f"Failed to create folder {folder_name}: {create_response.status_code}")
                        return False
            
            return True
            
        except Exception as e:
            print(f"Error creating folder structure: {e}")
            return False
    
    def check_file_exists(self, filename: str, folder_path: str) -> Tuple[bool, Optional[Dict]]:
        """
        Check if file already exists in SharePoint
        Returns: (exists: bool, file_metadata: dict or None)
        """
        try:
            config = self.cloud_config.get_sharepoint_config()
            site_url = config.get("site_url")
            base_folder = config.get("folder_path", "")
            
            if not site_url:
                return False, None
            
            site_id = self._get_site_id(site_url)
            if not site_id:
                return False, None
            
            drive_id = self._get_drive_id(site_id)
            if not drive_id:
                return False, None
            
            # Combine base folder with specific folder (same logic as upload_file)
            if base_folder and folder_path:
                full_folder_path = f"{base_folder.strip('/')}/{folder_path.strip('/')}"
            elif base_folder:
                full_folder_path = base_folder.strip('/')
            else:
                full_folder_path = folder_path.strip('/')
            
            # Build file path
            full_path = f"{full_folder_path.strip('/')}/{filename}" if full_folder_path else filename
            
            # Check if file exists
            url = f"{self.GRAPH_API_BASE}/drives/{drive_id}/root:/{full_path}"
            response = self._make_authenticated_request('GET', url)
            
            if response.status_code == 200:
                file_data = response.json()
                return True, {
                    "id": file_data.get("id"),
                    "name": file_data.get("name"),
                    "size": file_data.get("size"),
                    "lastModified": file_data.get("lastModifiedDateTime"),
                    "etag": file_data.get("eTag"),
                    "downloadUrl": file_data.get("@microsoft.graph.downloadUrl")
                }
            else:
                return False, None
                
        except Exception as e:
            print(f"Error checking file existence: {e}")
            return False, None
    
    def calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file for integrity check"""
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    
    def upload_file(self, file_path: Path, filename: str, folder_path: str, 
                   conflict_strategy: str = "rename") -> Dict[str, Any]:
        """
        Upload file to SharePoint
        
        Args:
            file_path: Local file path
            filename: Target filename in SharePoint
            folder_path: Target folder in SharePoint
            conflict_strategy: "overwrite", "rename", or "skip"
            
        Returns:
            Dict with upload result
        """
        try:
            # Validate inputs
            if not file_path.exists():
                return {"success": False, "error": "File does not exist"}
            
            config = self.cloud_config.get_sharepoint_config()
            site_url = config.get("site_url")
            base_folder = config.get("folder_path", "")
            
            if not site_url:
                return {"success": False, "error": "SharePoint site URL not configured"}
            
            # Get site and drive IDs
            site_id = self._get_site_id(site_url)
            if not site_id:
                return {"success": False, "error": "Could not get SharePoint site ID"}
            
            drive_id = self._get_drive_id(site_id)
            if not drive_id:
                return {"success": False, "error": "Could not get SharePoint drive ID"}
            
            # Combine base folder with specific folder
            if base_folder and folder_path:
                full_folder_path = f"{base_folder.strip('/')}/{folder_path.strip('/')}"
            elif base_folder:
                full_folder_path = base_folder.strip('/')
            else:
                full_folder_path = folder_path.strip('/')
            
            # Create folder structure if needed
            if not self.create_folder_if_needed(full_folder_path):
                return {"success": False, "error": "Could not create folder structure"}
            
            # Check if file exists
            exists, existing_file = self.check_file_exists(filename, full_folder_path)
            
            if exists and conflict_strategy == "skip":
                return {
                    "success": True,
                    "skipped": True,
                    "message": "File already exists, skipping upload",
                    "existing_file": existing_file
                }
            
            # Determine upload strategy based on file size
            file_size = file_path.stat().st_size
            
            if file_size < 4 * 1024 * 1024:  # Less than 4MB - simple upload
                result = self._simple_upload(file_path, filename, full_folder_path, drive_id, conflict_strategy)
            else:  # Large file - use resumable upload session
                result = self._resumable_upload(file_path, filename, full_folder_path, drive_id, conflict_strategy)
            
            # Add file hash for integrity verification
            if result.get("success"):
                result["file_hash"] = self.calculate_file_hash(file_path)
            
            return result
            
        except Exception as e:
            return {"success": False, "error": f"Upload failed: {str(e)}"}
    
    def _simple_upload(self, file_path: Path, filename: str, folder_path: str, 
                       drive_id: str, conflict_strategy: str) -> Dict[str, Any]:
        """Simple upload for small files (< 4MB)"""
        try:
            # Build upload URL
            full_path = f"{folder_path.strip('/')}/{filename}"
            
            # Set conflict behavior
            conflict_param = "@microsoft.graph.conflictBehavior="
            if conflict_strategy == "overwrite":
                conflict_param += "replace"
            elif conflict_strategy == "rename":
                conflict_param += "rename"
            else:
                conflict_param += "fail"
            
            url = f"{self.GRAPH_API_BASE}/drives/{drive_id}/root:/{full_path}:/content?{conflict_param}"
            
            # Upload file
            with open(file_path, 'rb') as f:
                additional_headers = {"Content-Type": "application/octet-stream"}
                response = self._make_authenticated_request('PUT', url, headers=additional_headers, data=f)
            
            if response.status_code in [200, 201]:
                file_data = response.json()
                return {
                    "success": True,
                    "file_id": file_data.get("id"),
                    "file_name": file_data.get("name"),
                    "web_url": file_data.get("webUrl"),
                    "size": file_data.get("size"),
                    "upload_method": "simple"
                }
            else:
                return {
                    "success": False,
                    "error": f"Upload failed with status {response.status_code}",
                    "details": response.text
                }
                
        except Exception as e:
            return {"success": False, "error": f"Simple upload error: {str(e)}"}
    
    def _resumable_upload(self, file_path: Path, filename: str, folder_path: str,
                         drive_id: str, conflict_strategy: str) -> Dict[str, Any]:
        """Resumable upload for large files (>= 4MB)"""
        try:
            # Create upload session
            full_path = f"{folder_path.strip('/')}/{filename}"
            session_url = f"{self.GRAPH_API_BASE}/drives/{drive_id}/root:/{full_path}:/createUploadSession"
            
            # Session request body
            session_data = {
                "item": {
                    "@microsoft.graph.conflictBehavior": 
                        "replace" if conflict_strategy == "overwrite" else "rename"
                }
            }
            
            # Create session
            session_response = self._make_authenticated_request(
                'POST', session_url, 
                headers={"Content-Type": "application/json"}, 
                json=session_data
            )
            
            if session_response.status_code != 200:
                return {
                    "success": False,
                    "error": f"Failed to create upload session: {session_response.status_code}",
                    "details": session_response.text
                }
            
            upload_url = session_response.json().get("uploadUrl")
            
            # Upload file in chunks
            file_size = file_path.stat().st_size
            
            with open(file_path, 'rb') as f:
                chunk_number = 0
                bytes_uploaded = 0
                
                while bytes_uploaded < file_size:
                    # Read chunk
                    chunk = f.read(self.settings.sharepoint_chunk_size)
                    chunk_size = len(chunk)
                    
                    # Calculate range
                    range_start = bytes_uploaded
                    range_end = min(bytes_uploaded + chunk_size - 1, file_size - 1)
                    
                    # Upload chunk
                    chunk_headers = {
                        "Content-Length": str(chunk_size),
                        "Content-Range": f"bytes {range_start}-{range_end}/{file_size}"
                    }
                    
                    chunk_response = requests.put(upload_url, headers=chunk_headers, data=chunk)
                    
                    if chunk_response.status_code not in [200, 201, 202]:
                        return {
                            "success": False,
                            "error": f"Chunk upload failed at byte {bytes_uploaded}",
                            "details": chunk_response.text
                        }
                    
                    bytes_uploaded += chunk_size
                    chunk_number += 1
                    
                    # Progress callback could go here
                    print(f"Uploaded chunk {chunk_number}: {bytes_uploaded}/{file_size} bytes")
            
            # Final response should contain file metadata
            if chunk_response.status_code in [200, 201]:
                file_data = chunk_response.json()
                return {
                    "success": True,
                    "file_id": file_data.get("id"),
                    "file_name": file_data.get("name"),
                    "web_url": file_data.get("webUrl"),
                    "size": file_data.get("size"),
                    "upload_method": "resumable",
                    "chunks_uploaded": chunk_number
                }
            else:
                return {
                    "success": False,
                    "error": "Upload completed but no file metadata returned"
                }
                
        except Exception as e:
            return {"success": False, "error": f"Resumable upload error: {str(e)}"}
    
    def get_file_metadata(self, file_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for an uploaded file"""
        try:
            url = f"{self.GRAPH_API_BASE}/drive/items/{file_id}"
            response = self._make_authenticated_request('GET', url)
            
            if response.status_code == 200:
                return response.json()
            else:
                return None
                
        except Exception as e:
            print(f"Error getting file metadata: {e}")
            return None
    
    def list_files(self, folder_path: str = "") -> List[Dict[str, Any]]:
        """List all files in a SharePoint folder"""
        try:
            config = self.cloud_config.get_sharepoint_config()
            site_url = config.get("site_url")
            if not site_url:
                raise ValueError("SharePoint site URL not configured")
            
            site_id = self._get_site_id(site_url)
            drive_id = self._get_drive_id(site_id)
            
            if not site_id or not drive_id:
                raise ValueError("Could not get SharePoint site or drive ID")
            
            # Build the API URL for listing files
            if folder_path:
                # List files in specific folder
                folder_path = folder_path.strip('/')
                url = f"{self.GRAPH_API_BASE}/sites/{site_id}/drives/{drive_id}/root:/{folder_path}:/children"
            else:
                # List files in root
                url = f"{self.GRAPH_API_BASE}/sites/{site_id}/drives/{drive_id}/root/children"
            
            response = self._make_authenticated_request('GET', url)
            
            if response.status_code == 200:
                data = response.json()
                files = []
                for item in data.get('value', []):
                    if 'file' in item:  # Only include files, not folders
                        files.append({
                            'id': item.get('id'),
                            'name': item.get('name'),
                            'size': item.get('size', 0),
                            'modified_date': item.get('lastModifiedDateTime'),
                            'download_url': item.get('@microsoft.graph.downloadUrl'),
                            'created_date': item.get('createdDateTime')
                        })
                return files
            else:
                print(f"Error listing files: {response.status_code} - {response.text}")
                return []
                
        except Exception as e:
            print(f"Error listing SharePoint files: {e}")
            return []

    def delete_file(self, file_id: str) -> bool:
        """Delete a file from SharePoint"""
        try:
            # Get site configuration to build correct URL
            config = self.cloud_config.get_sharepoint_config()
            site_url = config.get("site_url")
            if not site_url:
                raise ValueError("SharePoint site URL not configured")
            
            site_id = self._get_site_id(site_url)
            drive_id = self._get_drive_id(site_id)
            
            if not site_id or not drive_id:
                raise ValueError("Could not get SharePoint site or drive ID")
            
            # Use the correct URL format for SharePoint file deletion
            url = f"{self.GRAPH_API_BASE}/sites/{site_id}/drives/{drive_id}/items/{file_id}"
            response = self._make_authenticated_request('DELETE', url)
            
            # SharePoint returns 204 for successful deletion
            return response.status_code == 204
            
        except Exception as e:
            print(f"Error deleting SharePoint file: {e}")
            return False