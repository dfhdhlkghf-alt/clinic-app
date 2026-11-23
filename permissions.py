from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import get_db
import models

from auth import get_current_user   # ✅ الآن auth.py موجود


class RoleChecker:
    def __init__(self, allowed_roles: list):
        self.allowed_roles = allowed_roles

    def __call__(self, current_user: models.User = Depends(get_current_user)):
        if current_user.role not in self.allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Acceso denegado. Se requiere uno de estos roles: {self.allowed_roles}"
            )
        return current_user


def check_sucursal_access(user: models.User, target_sucursal_id: int):
    if user.role == "admin":
        return True
    if user.role in ["encargado", "fisioterapeuta"]:
        if user.sucursal_id != target_sucursal_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tienes permiso para acceder a datos de otra sucursal."
            )
        return True
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="No tienes permisos para acceder a esta información."
    )


def log_audit(db: Session, user_id: int, action: str, details: str = None):
    try:
        audit = models.AuditLog(
            user_id=user_id,
            action=action,
            details=details
        )
        db.add(audit)
        db.commit()
    except Exception as e:
        print(f"Error guardando auditoría: {e}")
        db.rollback()