"""
Certificacion File Manager - Handles file operations for certificaciones
"""

import os
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import re

from models.certificacion_document import CertificacionDocument
from models.licitacion_document import LicitacionDocument
from utils.file_manager import FileManager


class CertificacionFileManager:
    """Manages file operations specific to certificaciones"""
    
    def __init__(self, base_certificaciones_path: Path, licitaciones_path: Path):
        self.base_path = Path(base_certificaciones_path)
        self.licitaciones_path = Path(licitaciones_path)
        self.file_manager = FileManager()
        
        # Ensure base path exists
        self.base_path.mkdir(parents=True, exist_ok=True)
    
    def create_company_folder(self, certificacion: CertificacionDocument) -> Path:
        """
        Create company-specific folder structure
        Format: LIC-ID_LoteNum-LoteName_Company
        """
        folder_name = self._generate_company_folder_name(certificacion)
        company_folder = self.base_path / folder_name
        
        # Create main company folder
        company_folder.mkdir(exist_ok=True)
        
        # Create Adicionales subfolder
        adicionales_folder = company_folder / "Adicionales"
        adicionales_folder.mkdir(exist_ok=True)
        
        return company_folder
    
    def _generate_company_folder_name(self, certificacion: CertificacionDocument) -> str:
        """Generate standardized company folder name"""
        # Extract lote number and clean name
        lote_match = re.match(r'(\d+)\.\s*(.+)', certificacion.lote)
        if lote_match:
            lote_num = lote_match.group(1).zfill(2)
            lote_name = lote_match.group(2).strip()
        else:
            lote_num = "XX"
            lote_name = certificacion.lote
        
        # Clean and sanitize names
        lote_name_clean = self.file_manager.sanitize_for_filename(lote_name)
        company_clean = self.file_manager.sanitize_for_filename(certificacion.empresa)
        
        return f"{certificacion.nombre}_{lote_num}-{lote_name_clean}_{company_clean}"
    
    def get_company_folder_path(self, certificacion: CertificacionDocument) -> Path:
        """Get the path to company folder (create if doesn't exist)"""
        folder_name = self._generate_company_folder_name(certificacion)
        company_folder = self.base_path / folder_name
        
        if not company_folder.exists():
            company_folder = self.create_company_folder(certificacion)
        
        return company_folder
    
    def generate_certificacion_filename(self, certificacion_id: str, numero_cert: int, 
                                      version: str, file_extension: str) -> str:
        """
        Generate standardized filename for certificacion files
        Format: CertificacionID_NumCert_Version.ext
        """
        # Ensure extension doesn't start with a dot (we add it manually)
        if file_extension.startswith('.'):
            file_extension = file_extension[1:]
        
        return f"{certificacion_id}_Cert{numero_cert:02d}_{version}.{file_extension}"
    
    def attach_files_to_certificacion(self, certificacion: CertificacionDocument, 
                                    numero_certificacion: int, version: str,
                                    file_paths: List[Path]) -> List[Dict[str, Any]]:
        """
        Attach multiple files to a certificacion with proper naming and organization
        
        Returns:
            List of file operation results with paths and status
        """
        company_folder = self.get_company_folder_path(certificacion)
        results = []
        
        for i, source_path in enumerate(file_paths):
            try:
                if not source_path.exists():
                    results.append({
                        'source': str(source_path),
                        'status': 'error',
                        'message': 'Source file does not exist'
                    })
                    continue
                
                # Generate filename
                file_ext = self.file_manager.get_file_extension(source_path.name)
                
                # If multiple files, add index to version
                file_version = f"{version}_{i+1}" if len(file_paths) > 1 else version
                filename = self.generate_certificacion_filename(
                    certificacion.nombre, numero_certificacion, file_version, file_ext
                )
                
                destination = company_folder / filename
                
                # Handle conflicts
                if destination.exists():
                    backup_name = f"{destination.stem}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}{destination.suffix}"
                    backup_path = destination.parent / backup_name
                    shutil.move(str(destination), str(backup_path))
                    results.append({
                        'source': str(source_path),
                        'status': 'warning',
                        'message': f'Existing file backed up as {backup_name}'
                    })
                
                # Copy file
                shutil.copy2(str(source_path), str(destination))
                
                results.append({
                    'source': str(source_path),
                    'destination': str(destination),
                    'filename': filename,
                    'status': 'success',
                    'message': f'File attached successfully'
                })
                
            except Exception as e:
                results.append({
                    'source': str(source_path),
                    'status': 'error',
                    'message': f'Error copying file: {str(e)}'
                })
        
        return results
    
    def move_adicionales_files(self, certificacion: CertificacionDocument, 
                             adicionales_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Move adicionales files from licitaciones to certificaciones folder
        
        Args:
            certificacion: Target certificacion
            adicionales_ids: List of adicional licitacion IDs
            
        Returns:
            List of file operation results
        """
        company_folder = self.get_company_folder_path(certificacion)
        adicionales_folder = company_folder / "Adicionales"
        
        # Source folder for adicionales
        source_adicionales_folder = self.licitaciones_path / "adicionales"
        
        results = []
        
        for adicional_id in adicionales_ids:
            try:
                # Find files for this adicional
                pattern = f"{adicional_id}_*"
                matching_files = list(source_adicionales_folder.glob(pattern))
                
                if not matching_files:
                    results.append({
                        'adicional_id': adicional_id,
                        'status': 'warning',
                        'message': f'No files found for adicional {adicional_id}'
                    })
                    continue
                
                for source_file in matching_files:
                    try:
                        destination = adicionales_folder / source_file.name
                        
                        # Handle conflicts
                        if destination.exists():
                            backup_name = f"{destination.stem}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}{destination.suffix}"
                            backup_path = destination.parent / backup_name
                            shutil.move(str(destination), str(backup_path))
                        
                        # Move file
                        shutil.move(str(source_file), str(destination))
                        
                        results.append({
                            'adicional_id': adicional_id,
                            'source': str(source_file),
                            'destination': str(destination),
                            'status': 'success',
                            'message': f'Adicional file moved successfully'
                        })
                        
                    except Exception as e:
                        results.append({
                            'adicional_id': adicional_id,
                            'source': str(source_file),
                            'status': 'error',
                            'message': f'Error moving file: {str(e)}'
                        })
                        
            except Exception as e:
                results.append({
                    'adicional_id': adicional_id,
                    'status': 'error',
                    'message': f'Error processing adicional: {str(e)}'
                })
        
        return results
    
    def list_certificacion_files(self, certificacion: CertificacionDocument) -> Dict[str, List[Path]]:
        """
        List all files associated with a certificacion
        
        Returns:
            Dictionary with 'certificacion' and 'adicionales' file lists
        """
        company_folder = self.get_company_folder_path(certificacion)
        
        # Get certificacion files (in root of company folder)
        cert_pattern = f"{certificacion.nombre}_Cert*"
        certificacion_files = list(company_folder.glob(cert_pattern))
        
        # Get adicionales files
        adicionales_folder = company_folder / "Adicionales"
        adicionales_files = []
        if adicionales_folder.exists():
            adicionales_files = [f for f in adicionales_folder.iterdir() if f.is_file()]
        
        return {
            'certificacion': sorted(certificacion_files),
            'adicionales': sorted(adicionales_files)
        }
    
    def get_available_adicionales_files(self, parent_licitacion_name: str) -> List[Path]:
        """
        Get list of available adicionales files for a given parent licitacion
        
        Args:
            parent_licitacion_name: Name of the parent licitacion
            
        Returns:
            List of file paths for adicionales related to this licitacion
        """
        source_folder = self.licitaciones_path / "adicionales"
        
        if not source_folder.exists():
            return []
        
        # Find files that belong to adicionales of this parent licitacion
        # Pattern: ParentName-ADD_*, ParentName_*adicional*
        patterns = [
            f"{parent_licitacion_name}-ADD_*",
            f"{parent_licitacion_name}_*adicional*"
        ]
        
        files = []
        for pattern in patterns:
            files.extend(source_folder.glob(pattern))
        
        return sorted(files)
    
    def validate_file_for_certificacion(self, file_path: Path) -> Dict[str, Any]:
        """
        Validate if a file is suitable for certificacion attachment
        
        Returns:
            Validation result with status and details
        """
        result = {
            'valid': True,
            'warnings': [],
            'errors': []
        }
        
        if not file_path.exists():
            result['valid'] = False
            result['errors'].append('File does not exist')
            return result
        
        # Check file size (warn if > 50MB)
        size_mb = file_path.stat().st_size / (1024 * 1024)
        if size_mb > 50:
            result['warnings'].append(f'Large file size: {size_mb:.1f} MB')
        
        # Check file extension
        ext = file_path.suffix.lower()
        allowed_extensions = {'.pdf', '.xlsx', '.xls', '.docx', '.doc', '.dwg', '.rvt'}
        if ext not in allowed_extensions:
            result['warnings'].append(f'Unusual file type: {ext}')
        
        # Check filename for special characters
        if not self.file_manager.is_filename_safe(file_path.name):
            result['warnings'].append('Filename contains special characters that will be sanitized')
        
        return result
    
    def cleanup_empty_folders(self) -> List[str]:
        """
        Clean up empty company folders and return list of removed folders
        """
        removed_folders = []
        
        for folder in self.base_path.iterdir():
            if folder.is_dir():
                try:
                    # Check if folder is empty (including Adicionales subfolder)
                    is_empty = True
                    
                    for item in folder.rglob('*'):
                        if item.is_file():
                            is_empty = False
                            break
                    
                    if is_empty:
                        shutil.rmtree(folder)
                        removed_folders.append(folder.name)
                        
                except Exception as e:
                    print(f"Error cleaning up folder {folder}: {e}")
        
        return removed_folders
    
    def get_folder_size_info(self, certificacion: CertificacionDocument) -> Dict[str, Any]:
        """Get size information for company folder"""
        company_folder = self.get_company_folder_path(certificacion)
        
        total_size = 0
        file_count = 0
        
        for file_path in company_folder.rglob('*'):
            if file_path.is_file():
                total_size += file_path.stat().st_size
                file_count += 1
        
        return {
            'total_size_bytes': total_size,
            'total_size_mb': total_size / (1024 * 1024),
            'file_count': file_count,
            'folder_path': str(company_folder)
        }