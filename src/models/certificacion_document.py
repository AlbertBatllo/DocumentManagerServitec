from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import json
from pydantic import BaseModel, Field, computed_field


# Certificacion status codes (standardized across all document types)
CERTIFICACION_STATES = [
    "S0",  # Borrador
    "S1",  # Revisado por Delineación 
    "S2",  # Revisado por Técnico Especialista
    "S3",  # Revisado por Director Proyecto
    "S3A"  # Aprobado por propiedad/promotor
]

CERTIFICACION_STATE_DISPLAY_NAMES = {
    "S0": "Borrador",
    "S1": "Revisado por Delineación",
    "S2": "Revisado por Técnico Especialista", 
    "S3": "Revisado por Director Proyecto",
    "S3A": "Aprobado por propiedad/promotor"
}

CERTIFICACION_STATE_DESCRIPTIONS = {
    "S0": "Trabajo en proceso. Enviado sin revisión NUNCA SE ENVIA A PROPIEDAD EN ESTE ESTADO",
    "S1": "Revisado por Delineación. NUNCA SE ENVIA A PROPIEDAD EN ESTE ESTADO",
    "S2": "Revisado por Técnico Especialista.",
    "S3": "Revisado por Director Proyecto. SE PUEDE ENVIAR A PROPIEDAD EN ESTE ESTADO",
    "S3A": "Aprobado por propiedad/promotor."
}


class CertificacionEntry(BaseModel):
    """A single monthly certification entry"""
    numero_certificacion: int  # 0, 1, 2, 3... (monthly increments)
    fecha: str  # Date of certification
    importe_certificado: float  # Amount certified this month
    retencion: float  # Retention amount
    cuenta_prorrata: float  # Prorated account
    adicionales_ids: List[str] = Field(default_factory=list)  # IDs of adicionales included this month
    total_adicionales: float  # Sum of adicionales amounts
    total_certificado: float  # importe_certificado + total_adicionales
    porcentaje_completado: float  # Percentage completed (cumulative)
    author: str
    notes: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"))
    file_path: Optional[str] = None


class CertificacionDocument(BaseModel):
    """
    Certificacion document linked to approved Licitacion with Pydantic for performance and validation.
    
    Key Performance Improvements:
    - Pydantic provides automatic validation and serialization
    - Computed fields cache expensive financial calculations automatically
    - Eliminates manual caching and complex validation logic
    
    Updated: Uses Pydantic BaseModel instead of dataclass for better performance
    """
    # Inherited from Licitacion
    nombre: str  # Project name from Licitacion (primary identifier)
    lote: str  # Lot from Licitacion
    empresa: str  # Company from Licitacion (winning bidder)
    
    # Financial base data
    presupuesto_contratado: float  # Contracted budget (from approved Licitacion)
    licitacion_name: str  # Reference to parent Licitacion (changed from ID to name)
    
    # State management
    current_state: str = "S0"  # Current certification state
    
    # Certification entries (monthly updates)
    entries: List[CertificacionEntry] = Field(default_factory=list)

    @computed_field
    @property
    def numero_certificacion_actual(self) -> int:
        """Get current certification number (latest)"""
        if not self.entries:
            return 0
        return max(entry.numero_certificacion for entry in self.entries)

    @computed_field
    @property
    def cumulative_certificado(self) -> float:
        """Calculate total certified amount across all months"""
        if not self.entries:
            return 0.0
        return sum(entry.importe_certificado for entry in self.entries)

    @computed_field
    @property
    def cumulative_adicionales(self) -> float:
        """Calculate total adicionales across all months"""
        if not self.entries:
            return 0.0
        return sum(entry.total_adicionales for entry in self.entries)

    @computed_field
    @property
    def total_certificado_global(self) -> float:
        """Total certified including all adicionales"""
        return self.cumulative_certificado + self.cumulative_adicionales

    @computed_field
    @property
    def porcentaje_completado_actual(self) -> float:
        """Current completion percentage based on contracted budget (excludes adicionales)"""
        if self.presupuesto_contratado <= 0:
            return 0.0
        # Percentage is ONLY based on cumulative_certificado, NOT adicionales
        return (self.cumulative_certificado / self.presupuesto_contratado) * 100

    @computed_field
    @property
    def latest_entry(self) -> Optional[CertificacionEntry]:
        """Get the most recent certification entry"""
        if not self.entries:
            return None
        return max(self.entries, key=lambda x: x.numero_certificacion)

    @computed_field
    @property
    def lote_number(self) -> str:
        """Get just the lote number (first 2 digits)"""
        return self.lote[:2] if self.lote else "XX"

    @computed_field
    @property
    def lote_description(self) -> str:
        """Get just the lote description (everything after the number and dot)"""
        if not self.lote or ". " not in self.lote:
            return self.lote
        return self.lote.split(". ", 1)[1]

    def get_state_display_name(self, state: str = None) -> str:
        """Get display name for current or specified state"""
        state_to_check = state or self.current_state
        return CERTIFICACION_STATE_DISPLAY_NAMES.get(state_to_check, state_to_check)
    
    def get_state_description(self, state: str = None) -> str:
        """Get description for current or specified state"""
        state_to_check = state or self.current_state
        return CERTIFICACION_STATE_DESCRIPTIONS.get(state_to_check, "")
    
    def update_state(self, new_state: str) -> None:
        """Update certification state with validation"""
        if new_state not in CERTIFICACION_STATES:
            raise ValueError(f"State '{new_state}' no válido. Debe ser uno de: {CERTIFICACION_STATES}")
        self.current_state = new_state

    def add_entry(self, entry: CertificacionEntry) -> None:
        """Add a new monthly certification entry"""
        # Auto-calculate cumulative percentage (excluding adicionales)
        cumulative_importe = self.cumulative_certificado + entry.importe_certificado
        # Percentage is ONLY based on cumulative certificado, NOT adicionales
        entry.porcentaje_completado = (cumulative_importe / self.presupuesto_contratado) * 100 if self.presupuesto_contratado > 0 else 0
        
        self.entries.append(entry)

    def get_history(self) -> List[CertificacionEntry]:
        """Get all certification entries sorted by certification number"""
        return sorted(self.entries, key=lambda x: x.numero_certificacion)

    def get_adicionales_summary(self) -> Dict[str, float]:
        """Get summary of all adicionales used across all certifications"""
        adicionales_summary = {}
        for entry in self.entries:
            for adicional_id in entry.adicionales_ids:
                # This will be populated when we link to actual Adicionales
                adicionales_summary[adicional_id] = adicionales_summary.get(adicional_id, 0)
        return adicionales_summary

    def to_dict(self) -> Dict[str, Any]:
        """For backward compatibility - use model_dump() instead"""
        return self.model_dump()

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CertificacionDocument':
        """For backward compatibility - create from legacy data format"""
        # Support both old format (with id) and new format (nombre only)
        nombre = data.get("nombre") or data.get("id", "")
        
        # Handle both old and new licitacion reference field names
        licitacion_name = data.get("licitacion_name") or data.get("licitacion_id", "")
        
        # Handle state field (default to S0 for backward compatibility)
        current_state = data.get("current_state", "S0")
        
        # Handle legacy entry format
        entries_data = data.get("entries", [])
        entries = []
        for entry_data in entries_data:
            # Ensure all required fields are present with defaults
            entry_dict = {
                "numero_certificacion": entry_data.get("numero_certificacion", 0),
                "fecha": entry_data.get("fecha", datetime.now().strftime("%Y-%m-%d")),
                "importe_certificado": entry_data.get("importe_certificado", 0.0),
                "retencion": entry_data.get("retencion", 0.0),
                "cuenta_prorrata": entry_data.get("cuenta_prorrata", 0.0),
                "adicionales_ids": entry_data.get("adicionales_ids", []),
                "total_adicionales": entry_data.get("total_adicionales", 0.0),
                "total_certificado": entry_data.get("total_certificado", 0.0),
                "porcentaje_completado": entry_data.get("porcentaje_completado", 0.0),
                "author": entry_data.get("author", ""),
                "notes": entry_data.get("notes", ""),
                "timestamp": entry_data.get("timestamp", datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"))
            }
            entries.append(CertificacionEntry(**entry_dict))
        
        return cls(
            nombre=nombre,
            lote=data.get("lote", ""),
            empresa=data.get("empresa", ""),
            presupuesto_contratado=data.get("presupuesto_contratado", 0.0),
            licitacion_name=licitacion_name,
            current_state=current_state,
            entries=entries
        )

    @classmethod
    def create_from_licitacion(cls, licitacion: 'LicitacionDocument', presupuesto_contratado: float) -> 'CertificacionDocument':
        """Factory method to create Certificacion from approved Licitacion"""
        from models.licitacion_document import LicitacionDocument
        
        return cls(
            nombre=licitacion.name,
            lote=licitacion.lote,
            empresa=licitacion.company,
            presupuesto_contratado=presupuesto_contratado,
            licitacion_name=licitacion.name,
            current_state="S0",  # Start in development state
            entries=[]
        )


class CertificacionRepository:
    """Repository for managing certificacion documents"""
    
    def __init__(self, manifest_path: Path):
        self.manifest_path = manifest_path
        self.documents: Dict[str, CertificacionDocument] = {}
        self.load()

    def load(self) -> None:
        """Load documents from manifest file"""
        try:
            from utils.file_manager import FileManager
            data = FileManager.safe_json_read(str(self.manifest_path))
            
            # Handle both old format (id-based keys) and new format (name-based keys)
            for key, doc_data in data.items():
                document = CertificacionDocument.from_dict(doc_data)
                # Use the document's nombre as the key
                self.documents[document.nombre] = document
        except Exception as e:
            print(f"Error loading certificacion data: {e}")
            self.documents = {}

    def save(self) -> None:
        """Save documents to manifest file"""
        try:
            from utils.file_manager import FileManager
            data = {doc_nombre: doc.model_dump() for doc_nombre, doc in self.documents.items()}
            FileManager.safe_json_write(str(self.manifest_path), data)
        except Exception as e:
            print(f"Error saving certificacion data: {e}")
            raise

    def add_document(self, document: CertificacionDocument) -> None:
        """Add a new document"""
        self.documents[document.nombre] = document
        self.save()

    def get_document(self, doc_nombre: str) -> Optional[CertificacionDocument]:
        """Get document by nombre"""
        return self.documents.get(doc_nombre)
    
    def get_document_by_name(self, doc_nombre: str) -> Optional[CertificacionDocument]:
        """Alias for get_document for clarity"""
        return self.get_document(doc_nombre)

    def update_document(self, doc_nombre: str, document: CertificacionDocument) -> None:
        """Update existing document"""
        self.documents[doc_nombre] = document
        self.save()

    def get_all_documents(self) -> List[CertificacionDocument]:
        """Get all documents"""
        return list(self.documents.values())

    def document_exists(self, doc_nombre: str) -> bool:
        """Check if document exists"""
        return doc_nombre in self.documents

    def get_documents_by_lote(self, lote: str) -> List[CertificacionDocument]:
        """Get all documents for a specific lote"""
        return [doc for doc in self.documents.values() if doc.lote == lote]
    
    def find_similar_documents(self, query: str, max_results: int = 5) -> List[CertificacionDocument]:
        """Find documents with names similar to the query using fuzzy matching"""
        from utils.fuzzy_matcher import default_matcher
        
        all_nombres = list(self.documents.keys())
        similar_nombres = default_matcher.find_similar_names(query, all_nombres)
        
        results = []
        for nombre, score in similar_nombres[:max_results]:
            if nombre in self.documents:
                results.append(self.documents[nombre])
        
        return results
    
    def check_duplicate_name(self, nombre: str) -> Optional[str]:
        """Check if a name is too similar to existing documents. Returns conflicting name if found."""
        from utils.fuzzy_matcher import default_matcher
        
        for existing_nombre in self.documents.keys():
            if default_matcher.is_potential_duplicate(nombre, existing_nombre):
                return existing_nombre
        
        return None

    def get_documents_by_empresa(self, empresa: str) -> List[CertificacionDocument]:
        """Get all documents from a specific company"""
        return [doc for doc in self.documents.values() if doc.empresa.lower() == empresa.lower()]

    def get_financial_summary(self) -> Dict[str, Any]:
        """Get overall financial summary across all certifications"""
        total_presupuesto = sum(doc.presupuesto_contratado for doc in self.documents.values())
        total_certificado = sum(doc.cumulative_certificado for doc in self.documents.values())
        total_adicionales = sum(doc.cumulative_adicionales for doc in self.documents.values())
        
        return {
            "total_presupuesto_contratado": total_presupuesto,
            "total_certificado": total_certificado,
            "total_adicionales": total_adicionales,
            "total_global": total_certificado + total_adicionales,
            "porcentaje_global": (total_certificado / total_presupuesto * 100) if total_presupuesto > 0 else 0,
            "num_proyectos": len(self.documents)
        }