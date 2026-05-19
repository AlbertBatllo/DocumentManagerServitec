"""
Conflict Resolver Module
Handles version conflicts during cloud synchronization
"""

import hashlib
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
from enum import Enum

# Optional tkinter for user prompts
try:
    import tkinter as tk
    from tkinter import messagebox
    import tkinter.simpledialog as simpledialog
    HAS_TKINTER = True
except ImportError:
    HAS_TKINTER = False


class ConflictStrategy(Enum):
    """Conflict resolution strategies"""
    OVERWRITE = "overwrite"      # Always overwrite cloud version
    KEEP_BOTH = "keep_both"      # Keep both with different names
    SKIP = "skip"                # Skip upload if conflict
    ASK_USER = "ask_user"        # Ask user what to do
    NEWER_WINS = "newer_wins"     # Keep the newer version
    LARGER_WINS = "larger_wins"  # Keep the larger file


class ConflictResolver:
    """Resolves conflicts between local and cloud versions"""
    
    def __init__(self, default_strategy: ConflictStrategy = ConflictStrategy.ASK_USER):
        self.default_strategy = default_strategy
        self.resolution_cache = {}  # Cache user decisions for batch operations
    
    def calculate_file_hash(self, file_path: Path, algorithm: str = "md5") -> str:
        """Calculate hash of a file"""
        hash_obj = hashlib.md5() if algorithm == "md5" else hashlib.sha256()
        
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                hash_obj.update(byte_block)
        
        return hash_obj.hexdigest()
    
    def detect_conflict(self, local_file: Path, cloud_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Detect if there's a conflict between local and cloud versions
        
        Returns:
            Dict with conflict information:
            - has_conflict: bool
            - conflict_type: str (different_content, newer_cloud, different_state)
            - local_info: dict
            - cloud_info: dict
        """
        result = {
            "has_conflict": False,
            "conflict_type": None,
            "local_info": {},
            "cloud_info": cloud_metadata
        }
        
        if not cloud_metadata:
            # No cloud version, no conflict
            return result
        
        # Get local file info
        local_stat = local_file.stat()
        local_modified = datetime.fromtimestamp(local_stat.st_mtime)
        local_size = local_stat.st_size
        
        result["local_info"] = {
            "path": str(local_file),
            "size": local_size,
            "modified": local_modified.isoformat(),
            "hash": self.calculate_file_hash(local_file)
        }
        
        # Compare sizes first (quick check)
        cloud_size = cloud_metadata.get("size", 0)
        if local_size != cloud_size:
            result["has_conflict"] = True
            result["conflict_type"] = "different_size"
            return result
        
        # Compare hashes if available
        cloud_hash = cloud_metadata.get("md5") or cloud_metadata.get("etag")
        if cloud_hash:
            local_hash = result["local_info"]["hash"]
            if local_hash != cloud_hash:
                result["has_conflict"] = True
                result["conflict_type"] = "different_content"
                return result
        
        # Compare modification times
        cloud_modified_str = cloud_metadata.get("lastModified")
        if cloud_modified_str:
            try:
                cloud_modified = datetime.fromisoformat(cloud_modified_str.replace('Z', '+00:00'))
                # Remove timezone info for comparison
                cloud_modified = cloud_modified.replace(tzinfo=None)
                
                if cloud_modified > local_modified:
                    result["has_conflict"] = True
                    result["conflict_type"] = "newer_cloud"
                    return result
            except:
                pass  # Ignore date parsing errors
        
        # Check state conflicts from filename
        local_filename = local_file.name
        cloud_filename = cloud_metadata.get("name", "")
        
        if local_filename and cloud_filename:
            # Extract states from filenames (format: ID_Name_version_STATE.ext)
            local_parts = local_filename.rsplit('_', 1)
            cloud_parts = cloud_filename.rsplit('_', 1)
            
            if len(local_parts) > 1 and len(cloud_parts) > 1:
                local_state = local_parts[-1].split('.')[0]
                cloud_state = cloud_parts[-1].split('.')[0]
                
                if local_state != cloud_state:
                    result["has_conflict"] = True
                    result["conflict_type"] = "different_state"
                    result["local_info"]["state"] = local_state
                    result["cloud_info"]["state"] = cloud_state
        
        return result
    
    def resolve_conflict(self, conflict_info: Dict[str, Any], 
                        strategy: Optional[ConflictStrategy] = None) -> Dict[str, Any]:
        """
        Resolve a detected conflict
        
        Returns:
            Dict with resolution:
            - action: str (overwrite, rename, skip)
            - new_filename: str (if rename)
            - reason: str
        """
        if not conflict_info.get("has_conflict"):
            return {"action": "upload", "reason": "No conflict detected"}
        
        strategy = strategy or self.default_strategy
        conflict_type = conflict_info.get("conflict_type")
        
        # Check cache first
        cache_key = f"{conflict_info['local_info'].get('path')}:{conflict_type}"
        if cache_key in self.resolution_cache:
            return self.resolution_cache[cache_key]
        
        resolution = None
        
        if strategy == ConflictStrategy.OVERWRITE:
            resolution = {"action": "overwrite", "reason": "Strategy: always overwrite"}
            
        elif strategy == ConflictStrategy.SKIP:
            resolution = {"action": "skip", "reason": "Strategy: skip on conflict"}
            
        elif strategy == ConflictStrategy.KEEP_BOTH:
            resolution = self._generate_rename_resolution(conflict_info)
            
        elif strategy == ConflictStrategy.NEWER_WINS:
            resolution = self._resolve_by_date(conflict_info)
            
        elif strategy == ConflictStrategy.LARGER_WINS:
            resolution = self._resolve_by_size(conflict_info)
            
        elif strategy == ConflictStrategy.ASK_USER:
            resolution = self._ask_user_resolution(conflict_info)
        
        # Cache the resolution
        if resolution:
            self.resolution_cache[cache_key] = resolution
        
        return resolution or {"action": "skip", "reason": "No resolution determined"}
    
    def _generate_rename_resolution(self, conflict_info: Dict[str, Any]) -> Dict[str, Any]:
        """Generate a rename resolution"""
        local_path = Path(conflict_info["local_info"]["path"])
        base_name = local_path.stem
        extension = local_path.suffix
        
        # Add conflict suffix with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_filename = f"{base_name}_conflict_{timestamp}{extension}"
        
        return {
            "action": "rename",
            "new_filename": new_filename,
            "reason": "Keep both versions with different names"
        }
    
    def _resolve_by_date(self, conflict_info: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve by keeping the newer version"""
        conflict_type = conflict_info.get("conflict_type")
        
        if conflict_type == "newer_cloud":
            return {"action": "skip", "reason": "Cloud version is newer"}
        else:
            return {"action": "overwrite", "reason": "Local version is newer"}
    
    def _resolve_by_size(self, conflict_info: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve by keeping the larger file"""
        local_size = conflict_info["local_info"].get("size", 0)
        cloud_size = conflict_info["cloud_info"].get("size", 0)
        
        if cloud_size > local_size:
            return {"action": "skip", "reason": f"Cloud version is larger ({cloud_size} vs {local_size})"}
        else:
            return {"action": "overwrite", "reason": f"Local version is larger ({local_size} vs {cloud_size})"}
    
    def _ask_user_resolution(self, conflict_info: Dict[str, Any]) -> Dict[str, Any]:
        """Ask user how to resolve the conflict"""
        if not HAS_TKINTER:
            # No GUI available, default to skip
            return {"action": "skip", "reason": "No GUI available for user prompt"}
        
        try:
            local_info = conflict_info["local_info"]
            cloud_info = conflict_info["cloud_info"]
            conflict_type = conflict_info["conflict_type"]
            
            # Build message
            message = f"Conflicto detectado: {conflict_type}\n\n"
            message += f"Archivo local:\n"
            message += f"  Tamaño: {local_info.get('size', 'N/A')} bytes\n"
            message += f"  Modificado: {local_info.get('modified', 'N/A')}\n"
            
            if local_info.get('state'):
                message += f"  Estado: {local_info.get('state')}\n"
            
            message += f"\nArchivo en la nube:\n"
            message += f"  Tamaño: {cloud_info.get('size', 'N/A')} bytes\n"
            message += f"  Modificado: {cloud_info.get('lastModified', 'N/A')}\n"
            
            if cloud_info.get('state'):
                message += f"  Estado: {cloud_info.get('state')}\n"
            
            message += "\n¿Qué desea hacer?"
            
            # Create dialog
            root = tk.Tk()
            root.withdraw()  # Hide main window
            
            # Custom dialog with buttons
            dialog = tk.Toplevel(root)
            dialog.title("Conflicto de Versiones")
            dialog.geometry("500x300")
            
            # Message
            tk.Label(dialog, text=message, justify=tk.LEFT, padx=10, pady=10).pack()
            
            # Result variable
            result = {"action": "skip", "reason": "User cancelled"}
            
            def on_overwrite():
                result["action"] = "overwrite"
                result["reason"] = "User chose to overwrite"
                dialog.destroy()
            
            def on_rename():
                result["action"] = "rename"
                result["new_filename"] = self._generate_rename_resolution(conflict_info)["new_filename"]
                result["reason"] = "User chose to keep both"
                dialog.destroy()
            
            def on_skip():
                result["action"] = "skip"
                result["reason"] = "User chose to skip"
                dialog.destroy()
            
            # Buttons
            button_frame = tk.Frame(dialog)
            button_frame.pack(pady=10)
            
            tk.Button(button_frame, text="Sobrescribir", command=on_overwrite, width=15).pack(side=tk.LEFT, padx=5)
            tk.Button(button_frame, text="Mantener ambos", command=on_rename, width=15).pack(side=tk.LEFT, padx=5)
            tk.Button(button_frame, text="Omitir", command=on_skip, width=15).pack(side=tk.LEFT, padx=5)
            
            # Wait for user decision
            dialog.wait_window()
            root.destroy()
            
            return result
            
        except Exception as e:
            print(f"Error showing conflict dialog: {e}")
            return {"action": "skip", "reason": "Error showing dialog"}
    
    def clear_cache(self):
        """Clear the resolution cache"""
        self.resolution_cache.clear()
    
    def set_batch_mode(self, enabled: bool = True):
        """
        Enable/disable batch mode
        In batch mode, user is asked once for all similar conflicts
        """
        if enabled:
            self.resolution_cache.clear()
        else:
            self.resolution_cache.clear()