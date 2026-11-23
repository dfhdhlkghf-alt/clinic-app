from pydantic import AliasChoices, BaseModel, EmailStr, Field, computed_field
from datetime import date
from typing import List, Optional, Any, Dict

# Auth & User
class UserRegister(BaseModel):
    firstName: str = Field(..., validation_alias=AliasChoices('firstName', 'first_name'), max_length=50)
    lastName: str = Field(..., validation_alias=AliasChoices('lastName', 'last_name'), max_length=50)
    birthDate: date = Field(..., validation_alias=AliasChoices('birthDate', 'birth_date'))
    countryCode: str = Field("+52", validation_alias=AliasChoices('countryCode', 'country_code'), max_length=5)
    phone: str = Field(..., pattern=r"^[0-9]{10,12}$")
    email: EmailStr
    password: str = Field(..., min_length=6)
    privacy_accepted: Optional[bool] = None
    terms_accepted: Optional[bool] = None

    class Config:
        populate_by_name = True

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: EmailStr
    role: str
    semaforo: str
    sesiones_restantes: int
    is_active: bool

    @computed_field
    def nombre_completo(self) -> str:
        return f"{self.first_name} {self.last_name}"

    class Config:
        from_attributes = True

class UpdatePacienteSemaforo(BaseModel):
    user_id: int
    semaforo: str
    sesiones_asignadas: Optional[int] = 0

class ActivateAccountSchema(BaseModel):
    token: str

# --- ESQUEMAS TRABAJADOR / FISIOTERAPEUTA ---
class WorkerRegisterCheck(BaseModel):
    name: Optional[str] = Field(None, alias="nombre")
    nombre: Optional[str] = None
    email: EmailStr

    class Config:
        populate_by_name = True

class WorkerCheckInRequest(BaseModel):
    username: str

class AsistenciaRequest(BaseModel):
    worker_id: int

class AsistenciaResponse(BaseModel):
    id: int
    worker_id: int
    fecha: str
    hora_entrada: str
    hora_salida: Optional[str] = None

class WorkerVerifyPasswordRequest(BaseModel):
    username: str
    password: str

class CitaCheckInRequest(BaseModel):
    asistio: Optional[bool] = None
    attended: Optional[bool] = None

class FichaClinicaUpdate(BaseModel):
    user_id: Optional[int] = None
    notes: Optional[str] = None
    notas_clinicas: Optional[str] = None
    semaforo: Optional[str] = None
    assigned_sessions: Optional[int] = None
    sesiones_asignadas: Optional[int] = None

# Sucursales & Servicios
class SucursalResponse(BaseModel):
    id: int
    nombre: str
    direccion: str

    class Config:
        from_attributes = True

class ServicioResponse(BaseModel):
    id: int
    nombre: str
    descripcion: Optional[str]
    precio: float

    class Config:
        from_attributes = True

# Citas
class CitaCreate(BaseModel):
    user_id: int
    sucursal_id: int
    servicio_id: int
    fecha: date
    hora: str

class ConfirmarWhatsAppSchema(BaseModel):
    cita_id: int
    phone: Optional[str] = None
    user_id: Optional[int] = None

class CitaResponse(BaseModel):
    id: int
    user_id: int
    sucursal_id: int
    servicio_id: int
    fecha: date
    hora: str
    monto: float
    estado: str
    semaforo_al_agendar: str
    atendida: Optional[bool] = Field(None, alias="asistio")
    notas: Optional[str] = Field(None, alias="notas_clinicas")
    whatsapp_url: Optional[str] = None

    class Config:
        from_attributes = True
        populate_by_name = True

class CitaDetalladaResponse(BaseModel):
    id: int
    user_id: int
    fecha: date
    hora: str
    monto: float
    estado: str
    semaforo_al_agendar: str
    atendida: Optional[bool] = Field(None, alias="asistio")
    notas: Optional[str] = Field(None, alias="notas_clinicas")
    whatsapp_url: Optional[str] = None
    usuario: UserResponse
    sucursal: SucursalResponse
    servicio: ServicioResponse

    @computed_field
    def paciente_nombre(self) -> str:
        return f"{self.usuario.first_name} {self.usuario.last_name}" if self.usuario else ""

    @computed_field
    def sucursal_nombre(self) -> str:
        return self.sucursal.nombre if self.sucursal else ""

    @computed_field
    def servicio_nombre(self) -> str:
        return self.servicio.nombre if self.servicio else ""

    class Config:
        from_attributes = True
        populate_by_name = True

class ReprogramarCitaSchema(BaseModel):
    fecha: str
    hora: str

# Paquetes
class SesionItem(BaseModel):
    fecha: str
    hora: str

class AgendarPaqueteSchema(BaseModel):
    user_id: int
    sucursal_id: int
    servicio_id: int
    sesiones: List[SesionItem]

# Password Reset
class ForgotPasswordRequest(BaseModel):
    email: EmailStr
class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str
class BloqueoAgendaSchema(BaseModel):
        sucursal_id: int
        fecha: date
        hora_inicio: str
        hora_fin: str
        motivo: Optional[str] = "Bloqueo"