"""
Unified DWG XREF Extractor - LibreDWG Only

Single, clean implementation for extracting XREF references from DWG files.
Uses LibreDWG (dwg2dxf) for DWG to DXF conversion, then parses the DXF.

Extracts:
- DWG XREFs (external block references starting with X_)
- Image references (JPG, PNG, BMP, TIF, etc.)

This module replaces:
- dwg_xref_binary.py
- dwg_xref_dxf_only.py
- dwg_xref_extractor.py
- dwg_xref_hybrid.py
- dwg_xref_lightweight.py
- dwg_xref_opensource.py
- dwg_xref_self_contained.py
- dwg_xref_simple.py
- get_dwg_references.py
- get_dwg_references_optimized.py
"""

from pathlib import Path
from typing import List, Optional, Set
import tempfile
import subprocess
import shutil
import re
import logging
import sys
import os

logger = logging.getLogger(__name__)

# Supported image extensions for reference extraction
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.tif', '.tiff', '.gif', '.pcx'}

# Try to import ezdxf for better DXF parsing (optional)
try:
    import ezdxf
    EZDXF_AVAILABLE = True
except ImportError:
    EZDXF_AVAILABLE = False
    logger.info("ezdxf not available - using text-based DXF parsing")


class DwgXrefExtractor:
    """
    Extract XREF and image references from DWG files using LibreDWG.

    The extractor:
    1. Finds the dwg2dxf tool (bundled or system-installed)
    2. Converts DWG to DXF in a temp directory
    3. Parses the DXF to extract XREF references (X_*.dwg)
    4. Parses the DXF to extract image references (JPG, PNG, etc.)
    5. Returns the list of referenced files
    """

    def __init__(self):
        """Initialize the extractor and find dwg2dxf."""
        self.dwg2dxf_path = self._find_dwg2dxf()
        if self.dwg2dxf_path:
            logger.info(f"DWG XREF Extractor ready - dwg2dxf found at: {self.dwg2dxf_path}")
        else:
            logger.warning("DWG XREF Extractor: dwg2dxf not found - XREF extraction will not work")

    def _find_dwg2dxf(self) -> Optional[Path]:
        """
        Find dwg2dxf executable in multiple locations.

        Search order:
        1. Bundled in app (PyInstaller frozen)
        2. Project-relative location
        3. System PATH and common locations
        """
        candidates = []

        # 1. Check if running from bundled app (PyInstaller)
        if getattr(sys, 'frozen', False):
            if sys.platform == 'darwin':
                # macOS app bundle
                bundle_dir = Path(sys._MEIPASS) if hasattr(sys, '_MEIPASS') else Path(sys.executable).parent

                # Navigate to .app bundle root
                app_bundle = bundle_dir
                while app_bundle.parent != app_bundle and not str(app_bundle).endswith('.app'):
                    app_bundle = app_bundle.parent

                if str(app_bundle).endswith('.app'):
                    candidates.extend([
                        app_bundle / "Contents/Resources/libredwg/bin/dwg2dxf",
                        app_bundle / "Contents/Resources/dwg2dxf",
                    ])

                # Also check relative to _MEIPASS
                candidates.extend([
                    bundle_dir / "libredwg/bin/dwg2dxf",
                    bundle_dir / "dwg2dxf",
                ])

            elif sys.platform == 'win32':
                # Windows exe bundle
                bundle_dir = Path(sys._MEIPASS) if hasattr(sys, '_MEIPASS') else Path(sys.executable).parent
                candidates.extend([
                    bundle_dir / "libredwg/dwg2dxf.exe",
                    bundle_dir / "dwg2dxf.exe",
                ])

        # 2. Check project-relative locations (for development)
        try:
            script_dir = Path(__file__).parent.parent.parent  # src/utils -> src -> project root
            if sys.platform == 'win32':
                candidates.extend([
                    script_dir / "libredwg-win64/dwg2dxf.exe",
                    script_dir / "libredwg/dwg2dxf.exe",
                ])
            else:
                candidates.extend([
                    script_dir / "libredwg/bin/dwg2dxf",
                    script_dir / "libredwg/dwg2dxf",
                ])
        except (NameError, TypeError):
            pass  # __file__ not defined

        # 3. Check common system locations
        if sys.platform == 'win32':
            candidates.extend([
                Path("C:/Program Files/LibreDWG/dwg2dxf.exe"),
                Path("C:/LibreDWG/dwg2dxf.exe"),
            ])
        else:
            candidates.extend([
                Path.home() / "libredwg-install/usr/local/bin/dwg2dxf",
                Path("/usr/local/bin/dwg2dxf"),
                Path("/opt/homebrew/bin/dwg2dxf"),
            ])

        # 4. Check PATH
        which_result = shutil.which('dwg2dxf')
        if which_result:
            candidates.append(Path(which_result))

        # Find first existing candidate
        for candidate in candidates:
            if candidate and candidate.exists():
                logger.debug(f"Found dwg2dxf at: {candidate}")
                return candidate

        logger.warning("dwg2dxf not found in any location")
        return None

    def extract_references(self, dwg_file: Path) -> List[str]:
        """
        Extract XREF references from a DWG file.

        Args:
            dwg_file: Path to the DWG file

        Returns:
            List of referenced filenames (e.g., ["X_P1_ER.dwg", "X_Caratula.dwg"])
        """
        if not dwg_file.exists():
            logger.warning(f"DWG file not found: {dwg_file}")
            return []

        if not self.dwg2dxf_path:
            logger.error("Cannot extract references - dwg2dxf not found")
            return []

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # Copy DWG to temp directory (dwg2dxf outputs to same directory)
                temp_dwg = temp_path / dwg_file.name
                shutil.copy2(dwg_file, temp_dwg)

                # Convert DWG to DXF
                dxf_file = self._convert_to_dxf(temp_dwg, temp_path)

                if dxf_file and dxf_file.exists():
                    # Parse DXF and extract references
                    references = self._parse_dxf_for_xrefs(dxf_file)
                    logger.info(f"Extracted {len(references)} XREFs from {dwg_file.name}")
                    return references
                else:
                    logger.warning(f"DXF conversion failed for {dwg_file.name}")
                    return []

        except Exception as e:
            logger.error(f"XREF extraction failed for {dwg_file.name}: {e}")
            return []

    def extract_all_references(self, dwg_file: Path) -> dict:
        """
        Extract all references from a DWG file (XREFs and images).

        Args:
            dwg_file: Path to the DWG file

        Returns:
            Dictionary with 'dwg' and 'images' keys containing lists of filenames
            Example: {'dwg': ['X_P1_ER.dwg'], 'images': ['reference.jpg']}
        """
        result = {'dwg': [], 'images': []}

        if not dwg_file.exists():
            logger.warning(f"DWG file not found: {dwg_file}")
            return result

        if not self.dwg2dxf_path:
            logger.error("Cannot extract references - dwg2dxf not found")
            return result

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # Copy DWG to temp directory
                temp_dwg = temp_path / dwg_file.name
                shutil.copy2(dwg_file, temp_dwg)

                # Convert DWG to DXF
                dxf_file = self._convert_to_dxf(temp_dwg, temp_path)

                if dxf_file and dxf_file.exists():
                    # Parse DXF for XREF references
                    result['dwg'] = self._parse_dxf_for_xrefs(dxf_file)
                    # Parse DXF for image references
                    result['images'] = self._parse_dxf_for_images(dxf_file)

                    logger.info(f"Extracted {len(result['dwg'])} XREFs and {len(result['images'])} images from {dwg_file.name}")
                else:
                    logger.warning(f"DXF conversion failed for {dwg_file.name}")

        except Exception as e:
            logger.error(f"Reference extraction failed for {dwg_file.name}: {e}")

        return result

    def extract_image_references(self, dwg_file: Path) -> List[str]:
        """
        Extract image references from a DWG file.

        Args:
            dwg_file: Path to the DWG file

        Returns:
            List of referenced image filenames (e.g., ["reference.jpg", "logo.png"])
        """
        if not dwg_file.exists():
            logger.warning(f"DWG file not found: {dwg_file}")
            return []

        if not self.dwg2dxf_path:
            logger.error("Cannot extract references - dwg2dxf not found")
            return []

        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_path = Path(temp_dir)

                # Copy DWG to temp directory
                temp_dwg = temp_path / dwg_file.name
                shutil.copy2(dwg_file, temp_dwg)

                # Convert DWG to DXF
                dxf_file = self._convert_to_dxf(temp_dwg, temp_path)

                if dxf_file and dxf_file.exists():
                    images = self._parse_dxf_for_images(dxf_file)
                    logger.info(f"Extracted {len(images)} image references from {dwg_file.name}")
                    return images
                else:
                    logger.warning(f"DXF conversion failed for {dwg_file.name}")
                    return []

        except Exception as e:
            logger.error(f"Image extraction failed for {dwg_file.name}: {e}")
            return []

    def _convert_to_dxf(self, dwg_file: Path, output_dir: Path) -> Optional[Path]:
        """
        Convert DWG to DXF using dwg2dxf (LibreDWG).

        Args:
            dwg_file: Path to input DWG file
            output_dir: Directory for output DXF file

        Returns:
            Path to generated DXF file, or None if conversion failed
        """
        expected_dxf = output_dir / f"{dwg_file.stem}.dxf"

        try:
            # Build command
            cmd = [str(self.dwg2dxf_path), str(dwg_file)]

            # Set up environment for bundled libraries
            env = os.environ.copy()

            if sys.platform == 'darwin':
                # macOS: Add bundled library path
                lib_path = self.dwg2dxf_path.parent.parent / "lib"
                if lib_path.exists():
                    env['DYLD_LIBRARY_PATH'] = f"{lib_path}:{env.get('DYLD_LIBRARY_PATH', '')}"

            elif sys.platform == 'win32':
                # Windows: Add bundled DLL path
                dll_path = self.dwg2dxf_path.parent
                if dll_path.exists():
                    env['PATH'] = f"{dll_path};{env.get('PATH', '')}"

            # Run conversion
            result = subprocess.run(
                cmd,
                cwd=str(output_dir),
                capture_output=True,
                text=True,
                timeout=60,
                env=env
            )

            if expected_dxf.exists():
                logger.debug(f"DXF conversion successful: {expected_dxf}")
                return expected_dxf
            else:
                logger.warning(f"dwg2dxf did not produce output file. stderr: {result.stderr}")
                return None

        except subprocess.TimeoutExpired:
            logger.error(f"DXF conversion timeout for {dwg_file.name}")
            return None
        except FileNotFoundError:
            logger.error(f"dwg2dxf executable not found at {self.dwg2dxf_path}")
            return None
        except Exception as e:
            logger.error(f"DXF conversion error: {e}")
            return None

    def _parse_dxf_for_xrefs(self, dxf_file: Path) -> List[str]:
        """
        Parse DXF file to extract XREF references.

        Uses ezdxf if available, falls back to text parsing.

        Args:
            dxf_file: Path to DXF file

        Returns:
            Sorted list of XREF filenames
        """
        xrefs: Set[str] = set()

        # Method 1: Use ezdxf for structured parsing (preferred)
        if EZDXF_AVAILABLE:
            try:
                xrefs.update(self._parse_with_ezdxf(dxf_file))
            except Exception as e:
                logger.debug(f"ezdxf parsing failed, using text method: {e}")

        # Method 2: Text-based pattern matching (fallback/supplement)
        xrefs.update(self._parse_with_text(dxf_file))

        # Clean and normalize results
        cleaned = self._clean_xref_names(xrefs)
        return sorted(list(cleaned))

    def _parse_with_ezdxf(self, dxf_file: Path) -> Set[str]:
        """Parse DXF using ezdxf library."""
        xrefs = set()

        doc = ezdxf.readfile(str(dxf_file))

        # Check block definitions for XREF blocks
        for block in doc.blocks:
            if block.name.startswith('X_'):
                xref_name = block.name
                if not xref_name.lower().endswith('.dwg'):
                    xref_name += '.dwg'
                xrefs.add(xref_name)

        # Check model space for INSERT entities
        for entity in doc.modelspace():
            if entity.dxftype() == 'INSERT':
                block_name = entity.dxf.name
                if block_name.startswith('X_'):
                    if not block_name.lower().endswith('.dwg'):
                        block_name += '.dwg'
                    xrefs.add(block_name)

        return xrefs

    def _parse_with_text(self, dxf_file: Path) -> Set[str]:
        """Parse DXF using text pattern matching."""
        xrefs = set()

        try:
            with open(dxf_file, 'r', encoding='latin-1', errors='ignore') as f:
                content = f.read()

            # Pattern 1: X_RefName|LayerName (linetype definitions)
            pattern1 = r'X_[A-Za-z0-9\-_ ]{1,50}\|[A-Za-z0-9\-_ ]{1,50}'
            for match in re.finditer(pattern1, content):
                ref_part = match.group().split('|')[0].strip()
                if ref_part.startswith('X_'):
                    xrefs.add(ref_part)

            # Pattern 2: X_BlockName (block names starting with X_)
            pattern2 = r'(?:^|\s)X_[A-Za-z0-9\-_]{2,30}(?:\s|$)'
            for match in re.finditer(pattern2, content, re.MULTILINE):
                ref = match.group().strip()
                if ref.startswith('X_'):
                    xrefs.add(ref)

            # Pattern 3: DXF group code 2 values (block names)
            pattern3 = r'(?<=\n2\n)X_[A-Za-z0-9\-_ ]{2,30}(?=\n)'
            for match in re.finditer(pattern3, content):
                xrefs.add(match.group())

            # Pattern 4: File paths containing .dwg
            pattern4 = r'[A-Za-z0-9\-_ /\\\.]{1,100}\.dwg'
            for match in re.finditer(pattern4, content, re.IGNORECASE):
                filename = Path(match.group()).name
                if filename.upper().startswith('X_'):
                    xrefs.add(filename)

        except Exception as e:
            logger.error(f"Text parsing error: {e}")

        return xrefs

    def _parse_dxf_for_images(self, dxf_file: Path) -> List[str]:
        """
        Parse DXF file to extract image references.

        Looks for IMAGE entities and IMAGEDEF objects that reference external image files.

        Args:
            dxf_file: Path to DXF file

        Returns:
            Sorted list of image filenames
        """
        images: Set[str] = set()

        # Method 1: Use ezdxf for structured parsing (preferred)
        if EZDXF_AVAILABLE:
            try:
                images.update(self._parse_images_with_ezdxf(dxf_file))
            except Exception as e:
                logger.debug(f"ezdxf image parsing failed, using text method: {e}")

        # Method 2: Text-based pattern matching (fallback/supplement)
        images.update(self._parse_images_with_text(dxf_file))

        # Clean and normalize results
        cleaned = self._clean_image_names(images)
        return sorted(list(cleaned))

    def _parse_images_with_ezdxf(self, dxf_file: Path) -> Set[str]:
        """Parse DXF for image references using ezdxf library."""
        images = set()

        doc = ezdxf.readfile(str(dxf_file))

        # Check OBJECTS section for IMAGEDEF entities
        try:
            for obj in doc.objects:
                if obj.dxftype() == 'IMAGEDEF':
                    # IMAGEDEF has 'filename' attribute with the image path
                    if hasattr(obj.dxf, 'filename'):
                        filename = Path(obj.dxf.filename).name
                        images.add(filename)
        except Exception as e:
            logger.debug(f"Error reading IMAGEDEF objects: {e}")

        # Check all layouts for IMAGE entities
        try:
            for layout in doc.layouts:
                for entity in layout:
                    if entity.dxftype() == 'IMAGE':
                        # IMAGE entity references IMAGEDEF via handle
                        # The actual filename is in the IMAGEDEF
                        pass  # Already handled via IMAGEDEF above
        except Exception as e:
            logger.debug(f"Error reading IMAGE entities: {e}")

        return images

    def _parse_images_with_text(self, dxf_file: Path) -> Set[str]:
        """Parse DXF for image references using text pattern matching."""
        images = set()

        try:
            with open(dxf_file, 'r', encoding='latin-1', errors='ignore') as f:
                content = f.read()

            # Build pattern for image extensions
            extensions = '|'.join(ext.lstrip('.') for ext in IMAGE_EXTENSIONS)

            # Pattern 1: Full file paths ending with image extension
            # Matches paths like "C:\path\to\image.jpg" or "./REF/ref.png"
            # Must start with drive letter, ./, ../, or /
            pattern1 = rf'(?:[A-Za-z]:|\.{{1,2}})?[/\\][A-Za-z0-9\-_ /\\\.]+\.(?:{extensions})'
            for match in re.finditer(pattern1, content, re.IGNORECASE):
                filepath = match.group()
                # Extract just the filename
                filename = Path(filepath.replace('\\', '/')).name
                if filename and len(filename) > 5:  # At least "a.jpg" with some name
                    images.add(filename)

            # Pattern 2: IMAGEDEF section - look for filename after IMAGEDEF
            # DXF format: IMAGEDEF followed by filename on a line after group code 1
            pattern2 = r'IMAGEDEF[\s\S]*?(?<=\n1\n)([^\n]+\.(?:' + extensions + r'))(?=\n)'
            for match in re.finditer(pattern2, content, re.IGNORECASE):
                filepath = match.group(1)
                filename = Path(filepath.replace('\\', '/')).name
                if filename:
                    images.add(filename)

            # Pattern 3: Standalone image filenames on their own line (DXF group code values)
            # Must be a complete filename with at least 2 chars before extension
            pattern3 = rf'(?:^|\n)([A-Za-z][A-Za-z0-9\-_ ]*\.(?:{extensions}))(?:\n|$)'
            for match in re.finditer(pattern3, content, re.IGNORECASE | re.MULTILINE):
                filename = match.group(1).strip()
                if filename and len(filename) > 5:
                    images.add(filename)

        except Exception as e:
            logger.error(f"Text image parsing error: {e}")

        return images

    def _clean_image_names(self, images: Set[str]) -> Set[str]:
        """Clean and normalize image filenames."""
        cleaned = set()

        for image in images:
            # Normalize path separators and extract filename
            normalized = image.replace('\\', '/')
            name = Path(normalized).name

            # Clean up
            name = name.strip()

            # Verify it has a valid image extension and reasonable length
            if name and len(name) > 5:
                ext = Path(name).suffix.lower()
                if ext in IMAGE_EXTENSIONS:
                    cleaned.add(name)

        return cleaned

    def _clean_xref_names(self, xrefs: Set[str]) -> Set[str]:
        """Clean and normalize XREF names."""
        cleaned = set()

        for xref in xrefs:
            # Remove path prefixes
            name = Path(xref).name if '\\' in xref or '/' in xref else xref

            # Clean up
            name = name.strip()

            # Ensure .dwg extension
            if name and name.upper().startswith('X_'):
                if not name.lower().endswith('.dwg'):
                    name += '.dwg'
                cleaned.add(name)

        return cleaned

    def is_available(self) -> bool:
        """Check if XREF extraction is available."""
        return self.dwg2dxf_path is not None and self.dwg2dxf_path.exists()

    def get_info(self) -> dict:
        """Get information about the extractor configuration."""
        return {
            "available": self.is_available(),
            "dwg2dxf_path": str(self.dwg2dxf_path) if self.dwg2dxf_path else None,
            "ezdxf_available": EZDXF_AVAILABLE,
            "platform": sys.platform,
            "frozen": getattr(sys, 'frozen', False)
        }


# Global instance for convenience
_extractor: Optional[DwgXrefExtractor] = None


def get_extractor() -> DwgXrefExtractor:
    """Get the global DWG XREF extractor instance."""
    global _extractor
    if _extractor is None:
        _extractor = DwgXrefExtractor()
    return _extractor


def extract_dwg_references(dwg_file: Path) -> List[str]:
    """
    Extract XREF references from a DWG file.

    This is the main public API function.

    Args:
        dwg_file: Path to the DWG file

    Returns:
        List of referenced filenames (e.g., ["X_P1_ER.dwg", "X_Caratula.dwg"])

    Example:
        from utils.dwg_xref import extract_dwg_references
        refs = extract_dwg_references(Path("plano.dwg"))
        print(f"Found XREFs: {refs}")
    """
    return get_extractor().extract_references(dwg_file)


def get_references(dwg_file: Path) -> List[str]:
    """Alias for extract_dwg_references for backward compatibility."""
    return extract_dwg_references(dwg_file)


def is_xref_extraction_available() -> bool:
    """Check if XREF extraction is available."""
    return get_extractor().is_available()


def get_xref_extractor_info() -> dict:
    """Get information about the XREF extractor."""
    return get_extractor().get_info()


def extract_image_references(dwg_file: Path) -> List[str]:
    """
    Extract image references from a DWG file.

    Args:
        dwg_file: Path to the DWG file

    Returns:
        List of referenced image filenames (e.g., ["reference.jpg", "logo.png"])

    Example:
        from utils.dwg_xref import extract_image_references
        images = extract_image_references(Path("plano.dwg"))
        print(f"Found images: {images}")
    """
    return get_extractor().extract_image_references(dwg_file)


def extract_all_references(dwg_file: Path) -> dict:
    """
    Extract all references from a DWG file (XREFs and images).

    Args:
        dwg_file: Path to the DWG file

    Returns:
        Dictionary with 'dwg' and 'images' keys containing lists of filenames
        Example: {'dwg': ['X_P1_ER.dwg'], 'images': ['reference.jpg']}

    Example:
        from utils.dwg_xref import extract_all_references
        refs = extract_all_references(Path("plano.dwg"))
        print(f"Found XREFs: {refs['dwg']}")
        print(f"Found images: {refs['images']}")
    """
    return get_extractor().extract_all_references(dwg_file)


def get_image_extensions() -> set:
    """Get the set of supported image extensions."""
    return IMAGE_EXTENSIONS.copy()


# Test function
if __name__ == "__main__":
    print("DWG XREF Extractor - LibreDWG Only")
    print("=" * 50)

    info = get_xref_extractor_info()
    print(f"Configuration: {info}")
    print(f"Supported image extensions: {IMAGE_EXTENSIONS}")

    # Try to find a test file
    test_paths = [
        Path("planos_prueba/04 PLANTAS-ESTADO REFORMADO.dwg"),
        Path("test_dwg/sample.dwg"),
    ]

    for test_path in test_paths:
        if test_path.exists():
            print(f"\nTesting with: {test_path}")

            # Test all references extraction
            all_refs = extract_all_references(test_path)
            print(f"Found XREFs: {all_refs['dwg']}")
            print(f"Found images: {all_refs['images']}")
            break
    else:
        print("\nNo test DWG files found")
