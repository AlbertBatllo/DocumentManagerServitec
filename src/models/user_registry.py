from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from utils.file_manager import FileManager


class User:
    def __init__(self, name: str, email: str = "", active: bool = True):
        self.name = name
        self.email = email
        self.active = active
        self.last_seen = datetime.now().isoformat()
        self.created_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "email": self.email,
            "active": self.active,
            "last_seen": self.last_seen,
            "created_at": self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'User':
        user = cls(
            name=data.get("name", ""),
            email=data.get("email", ""),
            active=data.get("active", True)
        )
        user.last_seen = data.get("last_seen", datetime.now().isoformat())
        user.created_at = data.get("created_at", datetime.now().isoformat())
        return user


class UserRegistry:
    def __init__(self, global_root_path: Path = None):
        # UserRegistry is ALWAYS global, stored in root .project_manager
        # It does NOT depend on specific project paths
        # ALWAYS use PathHelper to handle App Translocation and read-only scenarios
        from utils.path_helper import PathHelper
        
        # Always use PathHelper for global configs - it handles read-only scenarios
        self.registry_path = PathHelper.get_config_file_path("users_registry.json")
        self.users: Dict[str, User] = {}
        self.load()
    
    def load(self) -> None:
        """Load users from registry file"""
        if self.registry_path.exists():
            try:
                data = FileManager.safe_json_read(str(self.registry_path))
                users_data = data.get("users", {})
                
                self.users = {}
                for name, user_data in users_data.items():
                    self.users[name] = User.from_dict(user_data)
                    
            except Exception as e:
                print(f"Error loading user registry: {e}")
                self.users = {}
        else:
            self._create_initial_registry()
    
    def _create_initial_registry(self) -> None:
        """Create initial registry file with default users"""
        try:
            self.registry_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Add some default users for assignment functionality
            default_users = [
                ("María García", "maria.garcia@servitec.com"),
                ("Carlos López", "carlos.lopez@servitec.com"), 
                ("Ana Rodríguez", "ana.rodriguez@servitec.com"),
                ("Luis Martínez", "luis.martinez@servitec.com"),
                ("Elena Sánchez", "elena.sanchez@servitec.com"),
                ("Ingeniero Técnico", "tecnico@servitec.com"),
                ("Supervisor", "supervisor@servitec.com"),
                ("Gerente de Proyecto", "gerente@servitec.com")
            ]
            
            for name, email in default_users:
                self.users[name] = User(name, email, active=True)
            
            self.save()
            print(f"DEBUG: Created initial user registry with {len(default_users)} default users")
        except OSError as e:
            raise RuntimeError(f"No se pudo crear el registro de usuarios: {e}")
    
    def save(self) -> None:
        """Save users to registry file"""
        try:
            data = {
                "users": {name: user.to_dict() for name, user in self.users.items()},
                "last_updated": datetime.now().isoformat(),
                "version": "1.0"
            }
            FileManager.safe_json_write(str(self.registry_path), data)
        except Exception as e:
            raise RuntimeError(f"No se pudo guardar el registro de usuarios: {e}")
    
    def add_user(self, name: str, email: str = "") -> bool:
        """Add a new user to registry"""
        if name in self.users:
            # Update last seen for existing user
            self.users[name].last_seen = datetime.now().isoformat()
            self.users[name].active = True
            self.save()
            return False  # User already existed
        
        self.users[name] = User(name, email)
        self.save()
        return True  # New user added
    
    def get_user(self, name: str) -> Optional[User]:
        """Get user by name"""
        return self.users.get(name)
    
    def get_all_users(self) -> List[User]:
        """Get all users"""
        return list(self.users.values())
    
    def get_active_users(self) -> List[User]:
        """Get only active users"""
        return [user for user in self.users.values() if user.active]
    
    def deactivate_user(self, name: str) -> bool:
        """Deactivate user"""
        if name in self.users:
            self.users[name].active = False
            self.save()
            return True
        return False
    
    def update_user_email(self, name: str, email: str) -> bool:
        """Update user email"""
        if name in self.users:
            self.users[name].email = email
            self.save()
            return True
        return False
    
    def register_user_activity(self, name: str) -> None:
        """Register that user is active (update last_seen)"""
        if name in self.users:
            self.users[name].last_seen = datetime.now().isoformat()
            self.save()
        else:
            # Auto-register unknown users
            self.add_user(name)