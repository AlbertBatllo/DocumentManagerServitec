"""
Plano Preset Manager
Handles creation and management of plano presets with project phases.
"""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from models.sqlite_document import SQLiteDocument


class PlanoPresetManager:
    """
    Manages preset planos for different project phases.
    Allows creation of stateless plano templates that teams can fill out.
    """
    
    # Available project phases
    PROJECT_PHASES = [
        "Implantación",
        "Proyecto Básico", 
        "Proyecto Ejecutivo",
        "Dirección Obra"
    ]
    
    def __init__(self, project_path: Path):
        self.project_path = project_path
        self.templates_path = self.project_path / "project_templates"
        self.presets_file = self.templates_path / "planos_presets.json"
        
        # Ensure templates directory exists
        self.templates_path.mkdir(exist_ok=True)
        
        # Initialize default presets if file doesn't exist
        if not self.presets_file.exists():
            self._create_default_presets()
    
    def _create_default_presets(self) -> None:
        """Create default preset template for construction projects"""
        default_presets = {
            "construction_project": {
                "name": "Proyecto de Construcción",
                "description": "Plantilla completa para proyectos de construcción con 90 planos organizados por fases",
                "presets": [
                    # Implantación (1 plano)
                    {"name": "04.1-Topográfico_Inicial", "phase": "Implantación", "description": "Topográfico Inicial"},
                    
                    # Proyecto Básico (7 planos)
                    {"name": "00-Portada", "phase": "Proyecto Básico", "description": "Portada"},
                    {"name": "01-Situación_y_emplazamiento", "phase": "Proyecto Básico", "description": "Situación y emplazamiento"},
                    {"name": "02.1-Ordenación", "phase": "Proyecto Básico", "description": "Ordenación"},
                    {"name": "02.2-Justificación_urbanística", "phase": "Proyecto Básico", "description": "Justificación urbanística"},
                    {"name": "03-Accesos", "phase": "Proyecto Básico", "description": "Accesos"},
                    {"name": "05-Condicionantes", "phase": "Proyecto Básico", "description": "Condicionantes (Inundabilidad, sismicidad...)"},
                    {"name": "I00.1-Acometidas", "phase": "Proyecto Básico", "description": "Acometidas"},
                    
                    # Proyecto Ejecutivo (76 planos)
                    {"name": "04.2-Topográfico_final", "phase": "Proyecto Ejecutivo", "description": "Topográfico final"},
                    {"name": "04.3-Topográfico_calculos", "phase": "Proyecto Ejecutivo", "description": "Topográfico calculos"},
                    
                    # Arquitectura
                    {"name": "A01-Plantas", "phase": "Proyecto Ejecutivo", "description": "Plantas"},
                    {"name": "A02-Fachadas", "phase": "Proyecto Ejecutivo", "description": "Fachadas"},
                    {"name": "A03-Secciones", "phase": "Proyecto Ejecutivo", "description": "Secciones"},
                    {"name": "A04-Cubierta", "phase": "Proyecto Ejecutivo", "description": "Cubierta"},
                    {"name": "A05-Albañilería", "phase": "Proyecto Ejecutivo", "description": "Albañilería"},
                    {"name": "A06-Soleras", "phase": "Proyecto Ejecutivo", "description": "Soleras"},
                    {"name": "A07-Acabados", "phase": "Proyecto Ejecutivo", "description": "Acabados"},
                    {"name": "A08-Carpintería", "phase": "Proyecto Ejecutivo", "description": "Carpintería"},
                    {"name": "A09-Vallado", "phase": "Proyecto Ejecutivo", "description": "Vallado"},
                    {"name": "A10-Accesibilidad_y_resbalacidad", "phase": "Proyecto Ejecutivo", "description": "Accesibilidad y resbalacidad"},
                    {"name": "A11-Detalle_aparcamiento", "phase": "Proyecto Ejecutivo", "description": "Detalle aparcamiento"},
                    {"name": "A12-Cartelería", "phase": "Proyecto Ejecutivo", "description": "Cartelería"},
                    {"name": "A13-Detalles", "phase": "Proyecto Ejecutivo", "description": "Detalles (remates, fijaciones, elementos cubierta, muros)"},
                    {"name": "A14-Equipamiento", "phase": "Proyecto Ejecutivo", "description": "Equipamiento (bolardos, biondas, carros...)"},
                    {"name": "A15-Detalles_SUA", "phase": "Proyecto Ejecutivo", "description": "Detalles SUA"},
                    {"name": "A16-Recogida_residuos", "phase": "Proyecto Ejecutivo", "description": "Recogida residuos"},
                    
                    # Estructura
                    {"name": "E01.1-Cimentación_planta_y_zooms", "phase": "Proyecto Ejecutivo", "description": "Cimentación planta y zooms"},
                    {"name": "E01.2-Zapatas_detalles_places_anclaje", "phase": "Proyecto Ejecutivo", "description": "Zapatas detalles, places anclaje"},
                    {"name": "E02-Muros_cerramiento", "phase": "Proyecto Ejecutivo", "description": "Muros cerramiento"},
                    {"name": "E03-Estructura_3D", "phase": "Proyecto Ejecutivo", "description": "Estructura 3D"},
                    {"name": "E04-Estructura_vertical", "phase": "Proyecto Ejecutivo", "description": "Estructura vertical (pilares)"},
                    {"name": "E05-Estructura_horitzontal", "phase": "Proyecto Ejecutivo", "description": "Estructura horitzontal (vigas)"},
                    {"name": "E06-Forjados", "phase": "Proyecto Ejecutivo", "description": "Forjados"},
                    {"name": "E07-Escaleras", "phase": "Proyecto Ejecutivo", "description": "Escaleras"},
                    {"name": "E08-Bancadas", "phase": "Proyecto Ejecutivo", "description": "Bancadas"},
                    {"name": "E09-Enanos", "phase": "Proyecto Ejecutivo", "description": "Enanos"},
                    
                    # Instalaciones
                    {"name": "I00.2-Instalaciones_urbanización", "phase": "Proyecto Ejecutivo", "description": "Instalaciones urbanización (urbanizacion con todas las lineas de Instalaciones marcades)"},
                    {"name": "I00.3-Instalaciones_generales", "phase": "Proyecto Ejecutivo", "description": "Instalaciones generales"},
                    
                    # PCI (Protección Contra Incendios)
                    {"name": "I01-PCI", "phase": "Proyecto Ejecutivo", "description": "PCI"},
                    {"name": "I01.0-Deposito_y_grupo_bombeo", "phase": "Proyecto Ejecutivo", "description": "Deposito y grupo bombeo"},
                    {"name": "I01.1-Hidrantes_exteriores", "phase": "Proyecto Ejecutivo", "description": "Hidrantes exteriores"},
                    {"name": "I01.2-Sectorización", "phase": "Proyecto Ejecutivo", "description": "Sectorización"},
                    {"name": "I01.3-Protección_passiva", "phase": "Proyecto Ejecutivo", "description": "Protección passiva"},
                    {"name": "I01.4-Recorridos", "phase": "Proyecto Ejecutivo", "description": "Recorridos"},
                    {"name": "I01.5-Espacio_exterior_seguro", "phase": "Proyecto Ejecutivo", "description": "Espacio exterior seguro"},
                    {"name": "I01.6-Señalética", "phase": "Proyecto Ejecutivo", "description": "Señalética"},
                    {"name": "I01.7-Extinción_manual", "phase": "Proyecto Ejecutivo", "description": "Extinción manual"},
                    {"name": "I01.8-Extinción_automàtica_y_puesto_de_control", "phase": "Proyecto Ejecutivo", "description": "Extinción automàtica y puesto de control"},
                    {"name": "I01.9-Deteccion_y_alarma", "phase": "Proyecto Ejecutivo", "description": "Deteccion y alarma"},
                    {"name": "I01.10-Depositos_humo_y_ventilación", "phase": "Proyecto Ejecutivo", "description": "Depositos humo y ventilación (solo ventilació CTE DB SI)"},
                    {"name": "I01.11-Accesibilidad_bomberos", "phase": "Proyecto Ejecutivo", "description": "Accesibilidad bomberos"},
                    
                    # Electricidad
                    {"name": "I02-ELECTRICIDAD", "phase": "Proyecto Ejecutivo", "description": "ELECTRICIDAD"},
                    {"name": "I02.1-Instalación_fotovoltaica", "phase": "Proyecto Ejecutivo", "description": "Instalación fotovoltaica"},
                    {"name": "I02.2-Alumbrado", "phase": "Proyecto Ejecutivo", "description": "Alumbrado"},
                    {"name": "I02.3-Potencia", "phase": "Proyecto Ejecutivo", "description": "Potencia (plantas y aparcamiento)"},
                    {"name": "I02.4-Canalizaciones", "phase": "Proyecto Ejecutivo", "description": "Canalizaciones"},
                    {"name": "I02.5-CGBT_y_subcuadros", "phase": "Proyecto Ejecutivo", "description": "CGBT y subcuadros"},
                    {"name": "I02.6-Red_de_tierras", "phase": "Proyecto Ejecutivo", "description": "Red de tierras"},
                    {"name": "I02.7-Unifilares", "phase": "Proyecto Ejecutivo", "description": "Unifilares"},
                    {"name": "I02.8-Centro_de_transformación", "phase": "Proyecto Ejecutivo", "description": "Centro de transformación"},
                    
                    # Pluviales
                    {"name": "I03-PLUVIALES", "phase": "Proyecto Ejecutivo", "description": "PLUVIALES"},
                    {"name": "I03.1-Pluviales_cubierta_y_detalles", "phase": "Proyecto Ejecutivo", "description": "Pluviales cubierta y detalles (sumideros, sifònica) incluyendo bajantes pozos rotura..."},
                    {"name": "I03.2-Pluviales_urbanización", "phase": "Proyecto Ejecutivo", "description": "Pluviales urbanización"},
                    
                    # Saneamiento
                    {"name": "I04-SANEAMIENTO", "phase": "Proyecto Ejecutivo", "description": "SANEAMIENTO"},
                    {"name": "I04.1-Saneamiento_interior", "phase": "Proyecto Ejecutivo", "description": "Saneamiento interior"},
                    {"name": "I04.2-Saneamiento_urbanización", "phase": "Proyecto Ejecutivo", "description": "Saneamiento urbanización"},
                    
                    # Fontanería
                    {"name": "I05-FONTANERIA", "phase": "Proyecto Ejecutivo", "description": "FONTANERIA"},
                    {"name": "I05.1-Fontanería", "phase": "Proyecto Ejecutivo", "description": "Fontanería (AFS y ACS)"},
                    {"name": "I05.2-Riego", "phase": "Proyecto Ejecutivo", "description": "Riego"},
                    
                    # Climatización
                    {"name": "I06-CLIMATIZACION", "phase": "Proyecto Ejecutivo", "description": "CLIMATIZACION"},
                    {"name": "I06-Climatización", "phase": "Proyecto Ejecutivo", "description": "Climatización"},
                    
                    # Ventilación
                    {"name": "I07-VENTILACION", "phase": "Proyecto Ejecutivo", "description": "VENTILACION"},
                    {"name": "I07-Ventilación", "phase": "Proyecto Ejecutivo", "description": "Ventilación"},
                    
                    # Pararrayos
                    {"name": "I08-PARARRAYOS", "phase": "Proyecto Ejecutivo", "description": "PARARRAYOS"},
                    {"name": "I08-Pararrayos", "phase": "Proyecto Ejecutivo", "description": "Pararrayos"},
                    
                    # Adicionales
                    {"name": "....-Adicionales", "phase": "Proyecto Ejecutivo", "description": "Adicionales (Megafonia, Control accessos, CCTV, BMS...)"},
                    
                    # Dirección Obra (6 planos)
                    {"name": "O01-Ubicación_residuos_casetas", "phase": "Dirección Obra", "description": "Ubicación residuos casetas"},
                    {"name": "O02-Desvios_provisionales", "phase": "Dirección Obra", "description": "Desvios provisionales"},
                    {"name": "O03-Conexiones_provisionales_obres", "phase": "Dirección Obra", "description": "Conexiones provisionales obres"},
                    {"name": "S01-Vallado", "phase": "Dirección Obra", "description": "Vallado (ESS)"},
                    {"name": "S02-Centros_salud", "phase": "Dirección Obra", "description": "Centros salud (ESS)"},
                    {"name": "S03-Plantas", "phase": "Dirección Obra", "description": "Plantas (ESS)"}
                ]
            }
        }
        
        # Save default presets
        with open(self.presets_file, 'w', encoding='utf-8') as f:
            json.dump(default_presets, f, indent=2, ensure_ascii=False)
    
    def get_available_presets(self) -> Dict[str, Any]:
        """Get all available preset templates"""
        try:
            with open(self.presets_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            # If file is corrupted, recreate defaults
            self._create_default_presets()
            with open(self.presets_file, 'r', encoding='utf-8') as f:
                return json.load(f)
    
    def get_presets_for_phase(self, phase: str) -> List[str]:
        """Get all preset names for a specific phase"""
        all_presets = self.get_available_presets()
        phase_presets = []
        
        for template in all_presets.values():
            for preset in template.get("presets", []):
                if preset.get("phase") == phase:
                    phase_presets.append(preset["name"])
        
        return sorted(list(set(phase_presets)))  # Remove duplicates and sort
    
    def create_preset_planos(self, db_manager, user_name: str, 
                           template_name: str, selected_presets: List[str] = None) -> List[str]:
        """
        Create preset planos from a template.
        
        Args:
            db_manager: Database manager instance
            user_name: Current user name
            template_name: Name of the template to use
            selected_presets: List of specific preset names to create (if None, creates all)
            
        Returns:
            List of created plano names
        """
        presets = self.get_available_presets()
        
        if template_name not in presets:
            raise ValueError(f"Template '{template_name}' not found")
        
        template = presets[template_name]
        created_planos = []
        
        for preset in template.get("presets", []):
            preset_name = preset["name"]
            preset_phase = preset["phase"]
            
            # Skip if specific presets were requested and this isn't one of them
            if selected_presets and preset_name not in selected_presets:
                continue
            
            # Check if plano already exists
            existing_doc = SQLiteDocument.load_from_database(
                db_manager, "planos", preset_name, user_name
            )
            
            if existing_doc:
                print(f"Skipping '{preset_name}' - already exists")
                continue
            
            # Create truly stateless preset document
            # This creates only the document record without any entries (truly stateless)
            try:
                # Create document directly using SQLiteDocument (no entries)
                document = SQLiteDocument.create_new(preset_name, "planos", db_manager, user_name)
                
                # Set the project phase
                document.project_phase = preset_phase
                
                # Leave author empty for preset templates
                document.autor = ""
                
                # Save to database
                document.save_to_database()
                
                print(f"Created stateless preset: '{preset_name}' (Phase: {preset_phase})")
            except Exception as e:
                print(f"Error creating preset '{preset_name}': {e}")
                continue
            created_planos.append(preset_name)
            print(f"Created preset plano: '{preset_name}' (Phase: {preset_phase})")
        
        return created_planos
    
    def create_custom_preset(self, db_manager, user_name: str, 
                           plano_name: str, phase: str) -> bool:
        """
        Create a single custom preset plano.
        
        Args:
            db_manager: Database manager instance
            user_name: Current user name
            plano_name: Name of the plano to create
            phase: Project phase for the plano
            
        Returns:
            True if created successfully, False if already exists
        """
        if phase not in self.PROJECT_PHASES:
            raise ValueError(f"Invalid phase '{phase}'. Must be one of: {', '.join(self.PROJECT_PHASES)}")
        
        # Check if plano already exists
        existing_doc = SQLiteDocument.load_from_database(
            db_manager, "planos", plano_name, user_name
        )
        
        if existing_doc:
            print(f"Plano '{plano_name}' already exists")
            return False
        
        # Create truly stateless preset document (same as create_preset_planos)
        try:
            # Create document directly using SQLiteDocument (no entries)
            document = SQLiteDocument.create_new(plano_name, "planos", db_manager, user_name)
            
            # Set the project phase
            document.project_phase = phase
            
            # Leave author empty for preset templates
            document.autor = ""
            
            # Save to database
            document.save_to_database()
            
        except Exception as e:
            print(f"Error creating custom preset '{plano_name}': {e}")
            return False
        print(f"Created custom preset plano: '{plano_name}' (Phase: {phase})")
        return True
    
    def get_phase_completion_status(self, db_manager, user_name: str) -> Dict[str, Dict[str, int]]:
        """
        Get completion status for each project phase.
        
        Returns:
            Dict with phase names as keys and completion stats as values.
            Each phase has: total, s3_count, s3a_count, completed_count
        """
        all_planos = SQLiteDocument.load_all_from_database(db_manager, "planos", user_name)
        
        phase_stats = {}
        for phase in self.PROJECT_PHASES:
            phase_stats[phase] = {
                "total": 0,
                "s3_count": 0,      # Revisado por Director Proyecto
                "s3a_count": 0,     # Aprobado por propiedad/promotor  
                "completed_count": 0 # S3 or S3A (ready for delivery)
            }
        
        for plano in all_planos:
            phase = getattr(plano, 'project_phase', 'Implantación')
            if phase not in phase_stats:
                phase = 'Implantación'  # Fallback for invalid phases
            
            phase_stats[phase]["total"] += 1
            
            current_state = plano.current_state
            if current_state == "S3":
                phase_stats[phase]["s3_count"] += 1
                phase_stats[phase]["completed_count"] += 1
            elif current_state == "S3A":
                phase_stats[phase]["s3a_count"] += 1
                phase_stats[phase]["completed_count"] += 1
        
        return phase_stats
    
    def get_phase_completion_summary(self, db_manager, user_name: str) -> str:
        """Get a human-readable summary of phase completion status"""
        stats = self.get_phase_completion_status(db_manager, user_name)
        
        summary_lines = []
        for phase, data in stats.items():
            if data["total"] > 0:
                completed = data["completed_count"]
                total = data["total"]
                percentage = (completed / total) * 100 if total > 0 else 0
                summary_lines.append(f"{phase}: {completed}/{total} planos listos ({percentage:.1f}%)")
        
        return "\n".join(summary_lines) if summary_lines else "No hay planos registrados"
    
    def add_custom_template(self, template_name: str, description: str, 
                          presets: List[Dict[str, str]]) -> None:
        """
        Add a custom template to the presets file.
        
        Args:
            template_name: Unique name for the template
            description: Description of the template
            presets: List of dicts with 'name' and 'phase' keys
        """
        all_presets = self.get_available_presets()
        
        # Validate preset data
        for preset in presets:
            if "name" not in preset or "phase" not in preset:
                raise ValueError("Each preset must have 'name' and 'phase' keys")
            if preset["phase"] not in self.PROJECT_PHASES:
                raise ValueError(f"Invalid phase '{preset['phase']}'. Must be one of: {', '.join(self.PROJECT_PHASES)}")
        
        # Add new template
        all_presets[template_name] = {
            "name": template_name,
            "description": description,
            "presets": presets
        }
        
        # Save updated presets
        with open(self.presets_file, 'w', encoding='utf-8') as f:
            json.dump(all_presets, f, indent=2, ensure_ascii=False)
        
        print(f"Added custom template: '{template_name}' with {len(presets)} presets")