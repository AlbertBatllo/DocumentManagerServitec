from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from utils.file_manager import FileManager


class Assignment:
    def __init__(self, document_id: str, document_name: str, from_state: str, 
                 to_state: str, assigned_by: str, assigned_users: List[str], 
                 notes: str = ""):
        self.document_id = document_id
        self.document_name = document_name
        self.from_state = from_state
        self.to_state = to_state
        self.assigned_by = assigned_by
        self.assigned_users = assigned_users
        self.notes = notes
        self.created_at = datetime.now().isoformat()
        self.status = "pending"  # pending, in_progress, completed, cancelled
        self.completed_at = None
        self.completed_by = None
        # Notification read status per user
        self.read_by = {}  # {username: read_timestamp}
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "document_name": self.document_name,
            "from_state": self.from_state,
            "to_state": self.to_state,
            "assigned_by": self.assigned_by,
            "assigned_users": self.assigned_users,
            "notes": self.notes,
            "created_at": self.created_at,
            "status": self.status,
            "completed_at": self.completed_at,
            "completed_by": self.completed_by,
            "read_by": self.read_by
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Assignment':
        assignment = cls(
            document_id=data.get("document_id", ""),
            document_name=data.get("document_name", ""),
            from_state=data.get("from_state", ""),
            to_state=data.get("to_state", ""),
            assigned_by=data.get("assigned_by", ""),
            assigned_users=data.get("assigned_users", []),
            notes=data.get("notes", "")
        )
        assignment.created_at = data.get("created_at", datetime.now().isoformat())
        assignment.status = data.get("status", "pending")
        assignment.completed_at = data.get("completed_at")
        assignment.completed_by = data.get("completed_by")
        assignment.read_by = data.get("read_by", {})
        return assignment
    
    def mark_completed(self, completed_by: str) -> None:
        """Mark assignment as completed"""
        self.status = "completed"
        self.completed_at = datetime.now().isoformat()
        self.completed_by = completed_by
    
    def mark_as_read(self, username: str) -> None:
        """Mark notification as read for a specific user"""
        self.read_by[username] = datetime.now().isoformat()
    
    def is_read_by_user(self, username: str) -> bool:
        """Check if notification has been read by user"""
        return username in self.read_by
    
    def is_unread_for_user(self, username: str) -> bool:
        """Check if this is an unread notification for user"""
        return (username in self.assigned_users and 
                self.status == "pending" and 
                not self.is_read_by_user(username))


class AssignmentManager:
    def __init__(self, project_path: Path = None):
        from utils.path_helper import PathHelper
        self.assignments_path = PathHelper.get_config_file_path("assignments.json", project_path)
        self.assignments: Dict[str, Assignment] = {}  # assignment_id -> Assignment
        self._next_id = 1
        self.load()
    
    def load(self) -> None:
        """Load assignments from file"""
        if self.assignments_path.exists():
            try:
                data = FileManager.safe_json_read(str(self.assignments_path))
                assignments_data = data.get("assignments", {})
                
                self.assignments = {}
                for assignment_id, assignment_data in assignments_data.items():
                    self.assignments[assignment_id] = Assignment.from_dict(assignment_data)
                
                self._next_id = data.get("next_id", 1)
                
            except Exception as e:
                print(f"Error loading assignments: {e}")
                self.assignments = {}
                self._next_id = 1
        else:
            self._create_initial_assignments()
    
    def _create_initial_assignments(self) -> None:
        """Create initial assignments file"""
        try:
            self.assignments_path.parent.mkdir(parents=True, exist_ok=True)
            self.save()
        except OSError as e:
            raise RuntimeError(f"No se pudo crear el archivo de asignaciones: {e}")
    
    def save(self) -> None:
        """Save assignments to file"""
        try:
            data = {
                "assignments": {assignment_id: assignment.to_dict() 
                             for assignment_id, assignment in self.assignments.items()},
                "next_id": self._next_id,
                "last_updated": datetime.now().isoformat(),
                "version": "1.0"
            }
            FileManager.safe_json_write(str(self.assignments_path), data)
        except Exception as e:
            raise RuntimeError(f"No se pudo guardar las asignaciones: {e}")
    
    def create_assignment(self, document_id: str, document_name: str, 
                         from_state: str, to_state: str, assigned_by: str, 
                         assigned_users: List[str], notes: str = "") -> str:
        """Create new assignment and return assignment ID"""
        assignment_id = f"ASSGN_{self._next_id:06d}"
        self._next_id += 1
        
        assignment = Assignment(
            document_id=document_id,
            document_name=document_name,
            from_state=from_state,
            to_state=to_state,
            assigned_by=assigned_by,
            assigned_users=assigned_users,
            notes=notes
        )
        
        self.assignments[assignment_id] = assignment
        self.save()
        return assignment_id
    
    def get_assignment(self, assignment_id: str) -> Optional[Assignment]:
        """Get assignment by ID"""
        return self.assignments.get(assignment_id)
    
    def assignment_exists(self, assignment_id: str) -> bool:
        """Check if assignment exists"""
        return assignment_id in self.assignments
    
    def get_assignments_for_user(self, username: str, status: str = None) -> List[Assignment]:
        """Get assignments for a specific user"""
        user_assignments = []
        for assignment in self.assignments.values():
            if username in assignment.assigned_users:
                if status is None or assignment.status == status:
                    user_assignments.append(assignment)
        
        # Sort by creation date (newest first)
        user_assignments.sort(key=lambda x: x.created_at, reverse=True)
        return user_assignments
    
    def get_assignments_for_document(self, document_id: str) -> List[Assignment]:
        """Get all assignments for a document"""
        doc_assignments = []
        for assignment in self.assignments.values():
            if assignment.document_id == document_id:
                doc_assignments.append(assignment)
        
        # Sort by creation date (newest first)
        doc_assignments.sort(key=lambda x: x.created_at, reverse=True)
        return doc_assignments
    
    def complete_assignment(self, assignment_id: str, completed_by: str) -> bool:
        """Mark assignment as completed"""
        if assignment_id in self.assignments:
            self.assignments[assignment_id].mark_completed(completed_by)
            self.save()
            return True
        return False
    
    def cancel_assignment(self, assignment_id: str) -> bool:
        """Cancel assignment"""
        if assignment_id in self.assignments:
            self.assignments[assignment_id].status = "cancelled"
            self.save()
            return True
        return False
    
    def get_pending_assignments(self) -> List[Assignment]:
        """Get all pending assignments"""
        pending = [a for a in self.assignments.values() if a.status == "pending"]
        pending.sort(key=lambda x: x.created_at, reverse=True)
        return pending
    
    def auto_complete_assignments_for_document_state(self, document_id: str, 
                                                   current_state: str, completed_by: str) -> int:
        """Auto-complete assignments when document state changes"""
        completed_count = 0
        for assignment in self.assignments.values():
            if (assignment.document_id == document_id and 
                assignment.to_state == current_state and 
                assignment.status == "pending"):
                assignment.mark_completed(completed_by)
                completed_count += 1
        
        if completed_count > 0:
            self.save()
        
        return completed_count
    
    def mark_assignment_as_read(self, assignment_id: str, username: str) -> bool:
        """Mark assignment notification as read for user"""
        if assignment_id in self.assignments:
            self.assignments[assignment_id].mark_as_read(username)
            self.save()
            return True
        return False
    
    def get_unread_count_for_user(self, username: str) -> int:
        """Get count of unread notifications for user"""
        count = 0
        for assignment in self.assignments.values():
            if assignment.is_unread_for_user(username):
                count += 1
        return count
    
    def get_unread_assignments_for_user(self, username: str) -> List[Assignment]:
        """Get unread assignments for a specific user"""
        unread = []
        for assignment in self.assignments.values():
            if assignment.is_unread_for_user(username):
                unread.append(assignment)
        
        # Sort by creation date (newest first)
        unread.sort(key=lambda x: x.created_at, reverse=True)
        return unread
    
    def delete_assignment(self, assignment_id: str) -> bool:
        """Delete an assignment by ID"""
        if assignment_id in self.assignments:
            del self.assignments[assignment_id]
            self.save()
            return True
        return False