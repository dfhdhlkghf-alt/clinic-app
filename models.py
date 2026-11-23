from datetime import datetime
import zoneinfo
from sqlalchemy import Column, Integer, String, Date, Boolean, ForeignKey, Numeric, Float, DateTime, Text, JSON
from sqlalchemy.orm import relationship
from database import Base
from security import decrypt_data

MEXICO_TZ = zoneinfo.ZoneInfo("America/Mexico_City")

def now_mexico():
    return datetime.now(MEXICO_TZ)

class Worker(Base):
    __tablename__ = "workers"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    username = Column(String(50), unique=True, index=True, nullable=True) 
    is_active = Column(Boolean, default=True)
    asistencias = relationship("AsistenciaWorker", back_populates="worker")

class AsistenciaWorker(Base):
    __tablename__ = "asistencias_workers"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=False)
    
    fecha = Column(DateTime, default=now_mexico)
    hora_entrada = Column(String, nullable=False)
    hora_salida = Column(String, nullable=True)
    
    worker = relationship("Worker", back_populates="asistencias")

class Sucursal(Base):
    __tablename__ = "sucursales"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    direccion = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)

    citas = relationship("Cita", back_populates="sucursal")
    usuarios = relationship("User", back_populates="sucursal")

class User(Base):
    __tablename__ = "users"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    
    password_hash = Column(String(255), nullable=False)
    encrypted_phone = Column(String(255), nullable=False)
    country_code = Column(String(10), default="+52")
    
    birth_date = Column(Date, nullable=False)
    
    role = Column(String(20), default="client") 
    is_active = Column(Boolean, default=False)

    semaforo = Column(String(20), default="ninguno")
    sesiones_restantes = Column(Integer, default=0)

    sucursal_id = Column(Integer, ForeignKey("sucursales.id"), nullable=True)

    citas = relationship("Cita", back_populates="usuario")
    sucursal = relationship("Sucursal", back_populates="usuarios")
    horarios = relationship("HorarioProfesional", back_populates="profesional")
    historial_clinico = relationship("HistoriaClinica", back_populates="paciente", uselist=False)

    @property
    def phone(self) -> str:
        return decrypt_data(self.encrypted_phone)

class Servicio(Base):
    __tablename__ = "servicios"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    descripcion = Column(String(255), nullable=True)
    precio = Column(Float, nullable=False)
    duracion_minutos = Column(Integer, default=60)
    is_active = Column(Boolean, default=True)

    citas = relationship("Cita", back_populates="servicio")

class Cita(Base):
    __tablename__ = "citas"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sucursal_id = Column(Integer, ForeignKey("sucursales.id"), nullable=False)
    servicio_id = Column(Integer, ForeignKey("servicios.id"), nullable=False)
    
    fecha = Column(Date, nullable=False)
    hora = Column(String(20), nullable=False)
    monto = Column(Numeric(10, 2), nullable=False)
    
    # حالة الموعد: pendiente (معلق بانتظار الدفع), confirmada (مؤكد), cancelada, completada
    estado = Column(String(20), default="confirmada")
    
    # ✅ حقول جديدة لطلب الزبون (الحجز المؤقت والوردية)
    expires_at = Column(DateTime, nullable=True) # متى ينتهي الحجز المؤقت (15 دقيقة)؟
    turno = Column(String(20), nullable=True)    # صباحي (Mañana) أو مسائي (Tarde)
    
    semaforo_al_agendar = Column(String(20), default="ninguno")
    
    asistio = Column(Boolean, nullable=True)
    notas_clinicas = Column(Text, nullable=True)

    usuario = relationship("User", back_populates="citas")
    sucursal = relationship("Sucursal", back_populates="citas")
    servicio = relationship("Servicio", back_populates="citas")

class HorarioProfesional(Base):
    __tablename__ = "horarios_profesionales"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    profesional_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sucursal_id = Column(Integer, ForeignKey("sucursales.id"), nullable=False)
    
    dia_semana = Column(Integer, nullable=False)
    hora_inicio = Column(String(10), nullable=False)
    hora_fin = Column(String(10), nullable=False)
    
    profesional = relationship("User", back_populates="horarios")
    sucursal = relationship("Sucursal")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=now_mexico)

class EventoAgenda(Base):
    __tablename__ = "eventos_agenda"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    profesional_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    sucursal_id = Column(Integer, ForeignKey("sucursales.id"), nullable=False)
    
    fecha = Column(Date, nullable=False)
    hora_inicio = Column(String(10), nullable=False)
    hora_fin = Column(String(10), nullable=False)
    motivo = Column(String(255), nullable=True)
    
    profesional = relationship("User")
    sucursal = relationship("Sucursal")
class HistoriaClinica(Base):
    __tablename__ = "historias_clinicas"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True) 
    
    datos_personales = Column(JSON, nullable=True) 
    
    # شيلنا حقل antecedentes القديم وحطنا التلاتة دول عشان يطابقوا الفرونت إند
    antecedentes_familiares = Column(JSON, nullable=True)
    antecedentes_personales = Column(JSON, nullable=True)
    habitos = Column(JSON, nullable=True)
    
    evaluaciones_especificas = Column(JSON, nullable=True) 
    notas_soap = Column(Text, nullable=True)
    
    fecha_actualizacion = Column(DateTime, default=now_mexico, onupdate=now_mexico)

    # السطر ده هو اللي بيمنع الإيرور
    paciente = relationship("User", back_populates="historial_clinico")