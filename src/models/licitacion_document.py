from typing import List, Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import json
from pydantic import BaseModel, Field, field_validator, computed_field, model_validator


# Fixed list of standardized lotes
LOTES_ESTANDAR = [
    "01. GEOTECNICO",
    "02. MOVIMIENTO DE TIERRAS", 
    "03. TOPOGRAFIA Y REPLANTEO",
    "03. CIMENTACION",  # Alternative name used in some projects
    "04. URBANIZACION",
    "05. CIMENTACIONES",
    "06. ESTRUCTURAS HORMIGON",
    "07. ESTRUCTURA DE MADERA",
    "08. ESTRUCTURA METALICA",
    "09. CERRAMIENTOS Y PARTICIONES",
    "10. CUBIERTAS E IMPERMEABILIZACIONES",
    "11. TECHADOS",
    "12. REVESTIMIENTOS",
    "13. PAVIMENTOS",
    "14. FONTANERIA",
    "15. ELECTRICIDAD",
    "16. CLIMATIZACION",
    "17. CARPINTERIA",
    "18. PINTURA",
    "19. VIDRIERIA",
    "20. EQUIPAMIENTO",
    "21. JARDINERIA",
    "22. LIMPIEZA Y GESTION DE RESIDUOS",
    "23. INSTALACIONES ESPECIALES",
    "24. SEGURIDAD Y SALUD",
    "25. GESTION Y ADMINISTRACION",
    "26. ELEVADORES",
    "27. SISTEMAS DE SEGURIDAD",
    "28. AUTOMATIZACION",
    "29. ENERGIA RENOVABLE",
    "30. TELECOMUNICACIONES",
    "31. CONTROL DE ACCESO",
    "32. GRUPO ELECTROGENO",
    "33. ASCENSOR",
    "34. PROTECCION CONTRA INCENDIOS (PCI)",
    "35. OBRA CIVIL"
]

# Document types within licitaciones
DOCUMENT_TYPES = [
    "presupuesto",  # General presupuesto type
    "licitacion",   # General licitacion type  
    "adicional"     # Adicional type
]

# Licitacion stages for workflow
LICITACION_STAGES = [
    "licitaciones",
    "presupuestos",
    "adicionales"
]

# Display names for stages
STAGE_DISPLAY_NAMES = {
    "licitaciones": "Licitaciones",
    "presupuestos": "Presupuestos",
    "adicionales": "Adicionales"
}

# Presupuesto types  
PRESUPUESTO_TYPES = [
    "presupuesto",
    "licitacion", 
    "adicional"
]

# Presupuesto statuses (standardized across all document types)
PRESUPUESTO_STATUSES = ["S0", "S1", "S2", "S3", "S3A"]

# Status display names (standardized system)
STATUS_DISPLAY_NAMES = {
    "S0": "Borrador",
    "S1": "Revisado por Delineación", 
    "S2": "Revisado por Técnico Especialista",
    "S3": "Revisado por Director Proyecto",
    "S3A": "Aprobado por propiedad/promotor"
}

# Type display names
TYPE_DISPLAY_NAMES = {
    "presupuesto": "Presupuesto",
    "licitacion": "Licitación",
    "adicional": "Adicional"
}

# Status help text
STATUS_HELP_TEXT = {
    "recibido": "El presupuesto ha sido recibido",
    "aceptado": "El presupuesto ha sido aceptado",
    "rechazado": "El presupuesto ha sido rechazado"
}

# Migration helper
def migrate_document_type(old_type: str) -> str:
    """Migrate old document types to new format"""
    migration_map = {
        "Presupuestos Recibidos": "presupuestos",
        "Presupuestos Aceptados": "presupuestos",
        "Mediciones": "licitaciones",
        "Adicionales": "adicionales"
    }
    return migration_map.get(old_type, old_type)


class LicitacionDocumentEntry(BaseModel):
    """A single entry for licitacion document"""
    version: str
    timestamp: str
    author: str
    notes: str
    file_path: Optional[str] = None
    status: Optional[str] = None
    stage: Optional[str] = None


class LicitacionDocument(BaseModel):
    """
    Licitacion document model with Pydantic for performance.
    
    Represents a licitacion (tender) document with company and lote information.
    """
    name: str  # Document name (primary identifier)
    lote: str  # From LOTES_ESTANDAR
    company: str  # Company name
    document_type: str  # From DOCUMENT_TYPES
    entries: List[LicitacionDocumentEntry] = Field(default_factory=list)
    
    # Optional fields that may not be present in all documents
    presupuesto_contratado: Optional[float] = None
    parent_licitacion_name: Optional[str] = None
    importe_adicional: Optional[float] = None
    valor: Optional[float] = None  # Required for presupuesto and adicional types
    pushed_to_certificacion: bool = False
    
    # User tracking fields
    autor: str = ""  # Original author/uploader of the document
    rev_tecnica: str = ""  # User who moved document to S2 (Revisado por Técnico Especialista)
    rev_gerencia: str = ""  # User who moved document to S3 (Revisado por Director Proyecto)

    @field_validator('lote')
    @classmethod
    def validate_lote(cls, v):
        if v and v not in LOTES_ESTANDAR:
            raise ValueError(f"Lote must be one of: {LOTES_ESTANDAR}")
        return v

    @field_validator('document_type')
    @classmethod
    def validate_document_type(cls, v):
        if v and v not in DOCUMENT_TYPES:
            raise ValueError(f"Document type must be one of: {DOCUMENT_TYPES}")
        return v

    @model_validator(mode='after')
    def validate_valor_for_document_type(self):
        """Validate valor field - required for presupuesto and adicional types"""
        if self.document_type in ["presupuesto", "adicional"]:
            if self.valor is None or self.valor <= 0:
                raise ValueError(f"Valor is required and must be greater than 0 for {self.document_type} documents")
        return self

    @computed_field
    @property
    def id(self) -> str:
        """Generate unique ID for the document"""
        return f"{self.name}_{self.lote_number:02d}_{self.company}"

    @computed_field
    @property
    def lote_number(self) -> int:
        """Extract lote number from lote string"""
        if self.lote and self.lote[:2].isdigit():
            return int(self.lote[:2])
        return 0

    @computed_field
    @property
    def lote_name(self) -> str:
        """Extract lote name (everything after the number)"""
        if self.lote and ". " in self.lote:
            return self.lote.split(". ", 1)[1]
        return self.lote

    @computed_field
    @property
    def current_entry(self) -> Optional[LicitacionDocumentEntry]:
        """Get the most recent entry"""
        if not self.entries:
            return None
        return max(self.entries, key=lambda x: x.timestamp)

    @computed_field
    @property
    def current_version(self) -> str:
        """Get current version"""
        current = self.current_entry
        return current.version if current else "1.0"

    @computed_field
    @property
    def filename(self) -> str:
        """Generate filename for the document"""
        current = self.current_entry
        version = current.version if current else "1.0"
        return f"{self.name}_{self.lote_number:02d}_{self.company}_v{version}.pdf"

    @computed_field
    @property
    def creation_date(self) -> str:
        """Get creation date from earliest entry"""
        if not self.entries:
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        earliest = min(self.entries, key=lambda x: x.timestamp)
        return earliest.timestamp
    
    @computed_field
    @property
    def current_stage(self) -> str:
        """Get current stage from latest entry"""
        current = self.current_entry
        if current and hasattr(current, 'stage') and current.stage:
            # Handle both direct stage access and attribute access
            stage = getattr(current, 'stage', None)
            if stage:
                return stage
        
        # Fallback: determine stage from document_type and status
        if self.document_type == "adicional":
            return "adicionales"
        elif self.document_type == "presupuesto":
            return "presupuestos"
        elif self.document_type == "licitacion":
            return "licitaciones"
        else:
            return "licitaciones"
    
    @computed_field
    @property
    def current_status(self) -> str:
        """Get current status from latest entry"""
        current = self.current_entry
        if current and hasattr(current, 'status'):
            status = getattr(current, 'status', None)
            if status:
                return status
        return "S0"  # Default status

    def add_entry(self, version: str, author: str, notes: str, file_path: Optional[str] = None, 
                  status: Optional[str] = None, stage: Optional[str] = None) -> None:
        """Add a new entry"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = LicitacionDocumentEntry(
            version=version,
            timestamp=timestamp,
            author=author,
            notes=notes,
            file_path=file_path,
            status=status,
            stage=stage
        )
        self.entries.append(entry)
    
    def can_push_to_certificacion(self) -> bool:
        """Check if this adicional can be pushed to certificaciones"""
        return (self.document_type == "adicionales" and 
                self.current_status == "A" and 
                not self.pushed_to_certificacion)
    
    def get_status_display_name(self) -> str:
        """Get human-readable status name"""
        return STATUS_DISPLAY_NAMES.get(self.current_status, self.current_status)
    
    def get_type_display_name(self) -> str:
        """Get human-readable type name"""
        return TYPE_DISPLAY_NAMES.get(self.document_type, self.document_type)


class LicitacionRepository:
    """Repository for managing licitacion documents"""
    
    def __init__(self, manifest_path: Path):
        self.manifest_path = manifest_path
        self.documents: Dict[str, LicitacionDocument] = {}
        self.load()
    
    def load(self) -> None:
        """Load documents from manifest file"""
        try:
            if self.manifest_path.exists():
                with open(self.manifest_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self.documents = {}
                for doc_id, doc_data in data.items():
                    # Convert entries
                    entries = [LicitacionDocumentEntry(**entry) for entry in doc_data.get('entries', [])]
                    doc_data['entries'] = entries
                    self.documents[doc_id] = LicitacionDocument(**doc_data)
            else:
                self.documents = {}
        except Exception as e:
            print(f"Error loading licitacion documents: {e}")
            self.documents = {}
    
    def save(self) -> None:
        """Save documents to manifest file"""
        try:
            self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
            
            data = {}
            for doc_id, document in self.documents.items():
                data[doc_id] = document.model_dump()
            
            with open(self.manifest_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving licitacion documents: {e}")
    
    def add_document(self, document: LicitacionDocument) -> None:
        """Add a new document"""
        self.documents[document.id] = document
        self.save()
    
    def get_document(self, doc_id: str) -> Optional[LicitacionDocument]:
        """Get a document by ID"""
        return self.documents.get(doc_id)
    
    def get_all_documents(self) -> List[LicitacionDocument]:
        """Get all documents"""
        return list(self.documents.values())
    
    def update_document(self, doc_id: str, document: LicitacionDocument) -> None:
        """Update a document"""
        self.documents[doc_id] = document
        self.save()
    
    def delete_document(self, doc_id: str) -> bool:
        """Delete a document"""
        if doc_id in self.documents:
            del self.documents[doc_id]
            self.save()
            return True
        return False
    
    def document_exists(self, name: str) -> bool:
        """Check if a document with the given name exists"""
        for doc in self.documents.values():
            if doc.name == name:
                return True
        return False
    
    def get_documents_by_lote(self, lote: str) -> List[LicitacionDocument]:
        """Get all documents for a specific lote"""
        return [doc for doc in self.documents.values() if doc.lote == lote]
    
    def get_documents_by_stage(self, stage: str) -> List[LicitacionDocument]:
        """Get all documents in a specific stage"""
        return [doc for doc in self.documents.values() if doc.current_stage == stage]
    
    def get_lote_status_summary(self) -> Dict[str, Dict[str, int]]:
        """Get summary of document counts per lote and stage"""
        summary = {}
        for doc in self.documents.values():
            lote = doc.lote
            stage = doc.current_stage
            
            if lote not in summary:
                summary[lote] = {}
            if stage not in summary[lote]:
                summary[lote][stage] = 0
            summary[lote][stage] += 1
        
        return summary
    
    def get_approved_adicionales(self) -> List[LicitacionDocument]:
        """Get all approved adicionales that can be pushed to certificaciones"""
        approved = []
        for doc in self.documents.values():
            if (doc.document_type == "adicionales" and 
                doc.current_status == "A" and 
                not doc.pushed_to_certificacion):
                approved.append(doc)
        return approved