import os
import jwt
import hmac
import hashlib
import urllib.parse
import zoneinfo
from dotenv import load_dotenv
from fastapi import FastAPI, Depends, HTTPException, status, Request, Response, BackgroundTasks
from fastapi.security import OAuth2PasswordBearer
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session, joinedload
from datetime import datetime, timedelta, timezone, date
from typing import List, Optional
import secrets
import string
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from security import hash_password, verify_password, encrypt_data
import models
import schemas
from permissions import log_audit
from database import engine, get_db
from email_service import (
    send_activation_email, 
    send_reset_password_email, 
    send_worker_passcode,
    send_worker_username_email,
    send_appointment_confirmation_email
)
from pydantic import BaseModel


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
# --- ZONA HORARIA MÉXICO ---
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    payload = verify_token(token)
    if payload is None:
        raise HTTPException(status_code=401, detail="Token inválido o expirado")
    
    # 👇 التعديل هنا: بنجيب الـ ID من التوكن
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=401, detail="Token no contiene usuario")
        
    # 👇 وبنبحث بيه في الداتابيز
    user = db.query(models.User).filter(models.User.id == int(user_id)).first()
    if user is None:
        raise HTTPException(status_code=401, detail="Usuario no encontrado")
    return user

MEXICO_TZ = zoneinfo.ZoneInfo("America/Mexico_City")

def now_mexico() -> datetime:
    return datetime.now(MEXICO_TZ)

def generar_password(longitud=8):
    caracteres = string.ascii_letters + string.digits
    return ''.join(secrets.choice(caracteres) for _ in range(longitud))

load_dotenv()
SECRET_KEY = os.getenv("JWT_SECRET_KEY", "secret_key_local_dev_12345")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

WHATSAPP_FISIOTECUIDA = os.getenv("WHATSAPP_FISIOTECUIDA", "5215622158737")

models.Base.metadata.create_all(bind=engine)

origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://fisiotecuida.com",
    "https://www.fisiotecuida.com"
]
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# ... باقي الأكواد بتاعتك ...

app = FastAPI()

origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def inicializar_datos_base(db: Session):
    servicios_base = [
        {"id": 1, "nombre": "Entrenamiento / Sesiones Online", "descripcion": "4 sesiones al mes de manera remota.", "precio": 650.00},
        {"id": 2, "nombre": "Entrenamiento Presencial", "descripcion": "4 sesiones al mes de 1 hora.", "precio": 900.00},
        {"id": 3, "nombre": "Consulta de Valoración", "descripcion": "Evaluación diagnóstica individual de 1 hora.", "precio": 400.00},
        {"id": 4, "nombre": "Sesión de Rehabilitación", "descripcion": "Sesión con atención personalizada basada en tu semáforo.", "precio": 250.00},
        {"id": 5, "nombre": "Fisio Senior", "descripcion": "Atención especializada para adultos mayores con horarios preferenciales.", "precio": 850.00},
    ]
    for s in servicios_base:
        db_servicio = db.query(models.Servicio).filter(models.Servicio.id == s["id"]).first()
        if not db_servicio:
            db.add(models.Servicio(**s))
        else:
            db_servicio.nombre = s["nombre"]
            db_servicio.descripcion = s["descripcion"]
            db_servicio.precio = s["precio"]

    if not db.query(models.Sucursal).first():
        s1 = models.Sucursal(nombre="Tacuba", direccion="Calzada México-Tacuba 737")
        s2 = models.Sucursal(nombre="Camarones", direccion="Primera Privada de Camarones 36")
        db.add_all([s1, s2])
    else:
        suc_tacuba = db.query(models.Sucursal).filter(models.Sucursal.nombre.ilike("%tacuba%")).first()
        if suc_tacuba:
            suc_tacuba.direccion = "Calzada México-Tacuba 737"

    if not db.query(models.Worker).filter(models.Worker.email == "fisioterapeuta@clinica.com").first():
        w_base = models.Worker(
            nombre="Fisioterapeuta General",
            email="fisioterapeuta@clinica.com",
            username="fisioterapeuta",
            is_active=True
        )
        db.add(w_base)

    db.commit()

@app.on_event("startup")
def startup_event():
    db = next(get_db())
    inicializar_datos_base(db)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    from jose import jwt
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str):
    from jose import jwt, JWTError
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None

# --- AUTH ---
@app.post("/api/register", status_code=status.HTTP_201_CREATED)
@app.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(user_data: schemas.UserRegister, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == user_data.email).first():
        raise HTTPException(status_code=400, detail="El correo ya está registrado.")

    nombre = getattr(user_data, 'first_name', None) or getattr(user_data, 'firstName', None)
    apellido = getattr(user_data, 'last_name', None) or getattr(user_data, 'lastName', None)
    fecha_nac = getattr(user_data, 'birth_date', None) or getattr(user_data, 'birthDate', None)
    codigo_pais = getattr(user_data, 'country_code', None) or getattr(user_data, 'countryCode', "+52")

    if not nombre or not apellido or not fecha_nac:
        raise HTTPException(status_code=400, detail="Faltan datos obligatorios (nombre, apellido o fecha de nacimiento).")

    new_user = models.User(
        first_name=nombre,
        last_name=apellido,
        birth_date=fecha_nac,
        country_code=codigo_pais,
        encrypted_phone=encrypt_data(user_data.phone),
        email=user_data.email,
        password_hash=hash_password(user_data.password),
        is_active=False,
        role="client"
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    activation_token = create_access_token(
        data={"sub": str(new_user.id), "type": "activation"},
        expires_delta=timedelta(hours=24)
    )
    try:
        await send_activation_email(new_user.email, activation_token)
    except Exception as e:
        print(f"Error enviando correo: {e}")

    return {"message": "Usuario registrado exitosamente. Revisa tu correo.", "email": new_user.email}

# --- ACTIVACIÓN DE CUENTA ---
def ejecutar_activacion(token: str, db: Session):
    payload = verify_token(token)
    if not payload or payload.get("type") != "activation":
        raise HTTPException(status_code=400, detail="Enlace inválido o expirado.")

    user = db.query(models.User).filter(models.User.id == int(payload.get("sub"))).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    user.is_active = True
    db.commit()
    return {"message": "Cuenta activada exitosamente."}

@app.get("/api/activar-cuenta")
@app.get("/activar-cuenta")
def activate_account_get(token: str, db: Session = Depends(get_db)):
    return ejecutar_activacion(token, db)

@app.post("/api/activar-cuenta")
@app.post("/activar-cuenta")
def activate_account_post(data: schemas.ActivateAccountSchema, db: Session = Depends(get_db)):
    return ejecutar_activacion(data.token, db)

# --- LOGIN ---
@app.post("/api/login")
@app.post("/login")
def login_user(credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == credentials.email).first()
    if not user or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Correo o contraseña incorrectos.")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Cuenta no activada. Revisa tu correo.")

    access_token = create_access_token(data={"sub": str(user.id), "role": user.role})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "role": user.role,
            "semaforo": user.semaforo,
            "sesiones_restantes": user.sesiones_restantes
        }
    }

# --- CATÁLOGOS ---
@app.get("/api/sucursales", response_model=List[schemas.SucursalResponse])
@app.get("/sucursales", response_model=List[schemas.SucursalResponse])
def get_sucursales(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    
    # 1. لو المستخدم أدمن، يشوف كل الفروع
    if current_user.role == "admin":
        return db.query(models.Sucursal).filter(models.Sucursal.is_active == True).all()
    
    # 2. لو مدير أو دكتور، يشوف فرعه بس
    elif current_user.role in ["encargado", "fisioterapeuta"]:
        if not current_user.sucursal_id:
            raise HTTPException(status_code=400, detail="El usuario no tiene sucursal asignada")
        
        # تسجيل الحركة في الـ Audit Log
        log_audit(db, current_user.id, "VIEW_SUCURSAL", f"Viewed sucursal {current_user.sucursal_id}")
        
        return db.query(models.Sucursal).filter(
            models.Sucursal.id == current_user.sucursal_id,
            models.Sucursal.is_active == True
        ).all()
        
    # 3. أي حد تاني (مريض) ممنوع
    else:
        raise HTTPException(status_code=403, detail="No tienes permiso para ver sucursales")
    
    
@app.get("/api/servicios", response_model=List[schemas.ServicioResponse])
@app.get("/servicios", response_model=List[schemas.ServicioResponse])
def get_servicios(db: Session = Depends(get_db)):
    return db.query(models.Servicio).filter(models.Servicio.is_active == True).all()

# --- ASIGNACIÓN DE SEMÁFORO ---
@app.post("/api/fisioterapeuta/asignar-semaforo")
def asignar_semaforo(data: schemas.UpdatePacienteSemaforo, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    
    # 1. التأكد إن اللي بيعدل دكتور أو مدير أو أدمن (مش مريض)
    if current_user.role not in ["admin", "encargado", "fisioterapeuta"]:
        raise HTTPException(status_code=403, detail="No tienes permiso para asignar semáforos")

    # 2. جلب المريض من الداتابيز
    user = db.query(models.User).filter(models.User.id == data.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Paciente no encontrado")

    # 3. التأكد من صلاحية الفرع (الأدمن بس اللي يقدر يعدل في أي فرع)
    if current_user.role != "admin":
        if user.sucursal_id != current_user.sucursal_id:
            raise HTTPException(status_code=403, detail="No puedes asignar semáforo a un paciente de otra sucursal")

    # 4. التأكد من صحة البيانات
    if data.semaforo not in ["rojo", "naranja", "verde", "ninguno"]:
        raise HTTPException(status_code=400, detail="Semáforo inválido")

    # 5. التعديل
    user.semaforo = data.semaforo
    user.sesiones_restantes = data.sesiones_asignadas
    db.commit()

    # 6. تسجيل الحركة في الـ Audit Log
    log_audit(db, current_user.id, "UPDATE_SEMAFORO", f"Cambió semáforo del paciente {user.id} a {data.semaforo}")

    return {"message": f"Semáforo {data.semaforo} asignado correctamente a {user.first_name}"}

# --- MOTOR DE DISPONIBILIDAD ---
@app.get("/api/citas/disponibilidad")
@app.get("/citas/disponibilidad")
def get_disponibilidad(sucursal_id: int, servicio_id: int, user_id: int, fecha: str, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    
    # ✅ حماية الفرع
    if current_user.role != "admin" and current_user.sucursal_id != sucursal_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para ver disponibilidad de otra sucursal")

    user = db.query(models.User).filter(models.User.id == user_id).first()
    servicio = db.query(models.Servicio).filter(models.Servicio.id == servicio_id).first()
    sucursal = db.query(models.Sucursal).filter(models.Sucursal.id == sucursal_id).first()

    if not user or not servicio or not sucursal:
        raise HTTPException(status_code=404, detail="Información de consulta no válida.")
    if servicio.id == 4 and user.semaforo == "ninguno":
        raise HTTPException(status_code=400, detail="Debes agendar primero una Consulta de Valoración antes de iniciar rehabilitación.")

    try:
        fecha_dt = datetime.strptime(fecha, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato YYYY-MM-DD requerido.")

    dia_semana = fecha_dt.weekday()
    nombre_suc = sucursal.nombre.lower()

    todos_los_horarios = []

    if "tacuba" in nombre_suc:
        if dia_semana <= 4:
            todos_los_horarios = ["08:00 AM", "09:00 AM", "10:00 AM", "11:00 AM", "12:00 PM", "01:00 PM", "02:00 PM", "03:00 PM", "04:00 PM", "05:00 PM", "06:00 PM", "07:00 PM", "08:00 PM"]
        elif dia_semana == 5:
            todos_los_horarios = ["08:00 AM", "09:00 AM", "10:00 AM", "11:00 AM", "12:00 PM", "01:00 PM", "02:00 PM", "03:00 PM"]
        elif dia_semana == 6:
            todos_los_horarios = ["09:00 AM", "10:00 AM", "11:00 AM", "12:00 PM"]

    elif "camarones" in nombre_suc:
        if dia_semana <= 4:
            todos_los_horarios = ["04:00 PM", "05:00 PM", "06:00 PM", "07:00 PM", "08:00 PM"]
        elif dia_semana == 5:
            todos_los_horarios = ["09:00 AM", "10:00 AM", "11:00 AM"]
        elif dia_semana == 6:
            todos_los_horarios = []

    horarios_senior_exclusivos = []
    if dia_semana <= 4:
        if "tacuba" in nombre_suc:
            horarios_senior_exclusivos = ["10:00 AM", "04:00 PM"]
        elif "camarones" in nombre_suc:
            horarios_senior_exclusivos = ["04:00 PM"]

    es_plan_senior = (servicio.id == 5 or "senior" in servicio.nombre.lower())

        # ✅ 1. جلب الحجوزات المؤكدة + الحجوزات المؤقتة التي لم تنتهِ صلاحيتها
    ahora = now_mexico()
    citas_existentes = db.query(models.Cita).filter(
        models.Cita.sucursal_id == sucursal_id,
        models.Cita.fecha == fecha_dt,
        models.Cita.estado.in_(["confirmada", "pendiente"])
    ).all()

    # تصفية الحجوزات المؤقتة (إذا انتهى وقتها نعتبرها ملغاة)
    citas_activas = []
    for c in citas_existentes:
        if c.estado == "pendiente" and c.expires_at and c.expires_at < ahora:
            continue # انتهى وقت الحجز المؤقت، تجاهله
        citas_activas.append(c)

    # ✅ 2. بناء التقويم (سعة 1 فقط لكل ساعة - منع التعارض تماماً)
    disponibilidad = []
    for h in todos_los_horarios:
        es_hora_senior = h in horarios_senior_exclusivos
        
        # إذا كانت الخدمة Senior ولم تكن الساعة مخصصة لكبار السن، تجاوزها
        if es_plan_senior and not es_hora_senior:
            continue
        
        # هل هذه الساعة محجوزة بأي موعد نشط؟
        citas_hora = [c for c in citas_activas if c.hora == h]
        
        # إذا كان هناك موعد واحد على الأقل، تصبح الساعة غير متاحة
        es_disponible = len(citas_hora) == 0

        # إذا كانت الساعة مخصصة لكبار السن، والمستخدم الحالي ليس كبيراً في السن
        if es_hora_senior and not es_plan_senior:
            es_disponible = False

        disponibilidad.append({
            "hora": h, 
            "disponible": es_disponible, 
            "estado": "ocupado" if len(citas_hora) > 0 else "libre"
        })

    return disponibilidad

# --- CITAS Y GESTIÓN DE CITAS ---

@app.get("/api/citas/usuario/{user_id}", response_model=List[schemas.CitaDetalladaResponse])
@app.get("/citas/usuario/{user_id}", response_model=List[schemas.CitaDetalladaResponse])
def get_citas_usuario(user_id: int, db: Session = Depends(get_db)):
    citas = db.query(models.Cita).options(
        joinedload(models.Cita.usuario),
        joinedload(models.Cita.sucursal),
        joinedload(models.Cita.servicio)
    ).filter(
        models.Cita.user_id == user_id,
        models.Cita.servicio_id.isnot(None)
    ).order_by(models.Cita.fecha.desc(), models.Cita.hora.desc()).all()
    
    return [c for c in citas if c.servicio is not None]

@app.post("/api/citas/agendar", status_code=status.HTTP_201_CREATED)
@app.post("/citas/agendar", status_code=status.HTTP_201_CREATED)
async def agendar_cita(cita_data: schemas.CitaCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    
    # ✅ 1. حماية الأجندة
    if current_user.role != "admin" and current_user.sucursal_id != cita_data.sucursal_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para agendar citas en otra sucursal")

    user = db.query(models.User).filter(models.User.id == cita_data.user_id).first()
    servicio = db.query(models.Servicio).filter(models.Servicio.id == cita_data.servicio_id).first()
    sucursal = db.query(models.Sucursal).filter(models.Sucursal.id == cita_data.sucursal_id).first()

    if not user or not servicio or not sucursal:
        raise HTTPException(status_code=404, detail="Usuario, servicio o sucursal no encontrado.")

    # ✅ 2. التحقق من تداخل المواعيد (منع الحجز المكرر)
    ahora = now_mexico()
    conflicto = db.query(models.Cita).filter(
        models.Cita.sucursal_id == cita_data.sucursal_id,
        models.Cita.fecha == cita_data.fecha,
        models.Cita.hora == cita_data.hora,
        models.Cita.estado.in_(["confirmada", "pendiente"])
    ).all()

    for c in conflicto:
        # إذا كان الحجز مؤكداً، أو كان معلقاً ولم تنتهِ مدته (15 دقيقة)
        if c.estado == "confirmada" or (c.estado == "pendiente" and c.expires_at and c.expires_at > ahora):
            raise HTTPException(
                status_code=400, 
                detail=f"Lo sentimos, la sesión de las {cita_data.hora} ya está ocupada. Por favor, elige otro horario."
            )

    # ✅ 3. تطبيق قاعدة الزبون: المريض الجديد يدفع 100 MXN (يُحجز مؤقتاً 15 دقيقة)
    tiene_citas = db.query(models.Cita).filter(models.Cita.user_id == cita_data.user_id).first()
    es_nuevo = not tiene_citas
    
    nuevo_estado = "pendiente" if es_nuevo else "confirmada"
    tiempo_expiracion = ahora + timedelta(minutes=15) if es_nuevo else None

    # تحديد الوردية (صباحي/مسائي) بناءً على الساعة
    try:
        hora_int = int(cita_data.hora.split(":")[0])
        turno = "Mañana" if hora_int < 12 else "Tarde"
    except:
        turno = "Mañana"

    # ✅ 4. إنشاء الموعد
    nueva_cita = models.Cita(
        user_id=cita_data.user_id,
        sucursal_id=cita_data.sucursal_id,
        servicio_id=cita_data.servicio_id,
        fecha=cita_data.fecha,
        hora=cita_data.hora,
        monto=servicio.precio,
        estado=nuevo_estado,          
        expires_at=tiempo_expiracion, 
        turno=turno,                  
        semaforo_al_agendar=user.semaforo
    )

    db.add(nueva_cita)
    db.commit()
    db.refresh(nueva_cita)

    # ✅ 5. إرسال إيميل التأكيد
    fechas_horas = [{"fecha": str(cita_data.fecha), "hora": cita_data.hora}]
    background_tasks.add_task(
        send_appointment_confirmation_email,
        email=user.email,
        nombre_paciente=f"{user.first_name} {user.last_name}",
        servicio=servicio.nombre,
        sucursal=sucursal.nombre,
        direccion=sucursal.direccion,
        fechas_horas=fechas_horas
    )

    # ✅ 6. تجهيز الرد للواجهة (الفرونت إند)
    mensaje_encoded = urllib.parse.quote("Listo reserve mi cita")
    whatsapp_link = f"https://wa.me/{WHATSAPP_FISIOTECUIDA}?text={mensaje_encoded}"

    res = schemas.CitaResponse.model_validate(nueva_cita)
    res_dict = res.model_dump()
    res_dict["whatsapp_url"] = whatsapp_link
    
    # إرسال المتغيرات الجديدة
    res_dict["requiere_pago"] = es_nuevo
    res_dict["mensaje_extra"] = "Tienes 15 minutos para pagar el anticipo de $100 MXN." if es_nuevo else ""
    
    return res_dict

@app.post("/api/citas/agendar-paquete", status_code=status.HTTP_201_CREATED)
@app.post("/citas/agendar-paquete", status_code=status.HTTP_201_CREATED)
async def agendar_paquete_citas(req: schemas.AgendarPaqueteSchema, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == req.user_id).first()
    servicio = db.query(models.Servicio).filter(models.Servicio.id == req.servicio_id).first()
    sucursal = db.query(models.Sucursal).filter(models.Sucursal.id == req.sucursal_id).first()

    if not user or not servicio or not sucursal:
        raise HTTPException(status_code=404, detail="Usuario, servicio o sucursal no encontrado.")

    if not req.sesiones:
        raise HTTPException(status_code=400, detail="Debes proporcionar al menos una sesión.")

    cant_sesiones = len(req.sesiones)
    es_rehabilitacion = servicio.id == 4 or "rehabilitaci" in servicio.nombre.lower()

    if es_rehabilitacion:
        if user.sesiones_restantes < cant_sesiones:
            raise HTTPException(
                status_code=400, 
                detail=f"Solo tienes {user.sesiones_restantes} sesión(es) disponibles para agendar."
            )

    monto_por_sesion = servicio.precio / cant_sesiones
    citas_creadas = []
    fechas_horas = []

    for s in req.sesiones:
        try:
            fecha_obj = datetime.strptime(s.fecha, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Formato de fecha inválido: {s.fecha}")

        ocupada = db.query(models.Cita).filter(
            models.Cita.sucursal_id == req.sucursal_id,
            models.Cita.fecha == fecha_obj,
            models.Cita.hora == s.hora,
            models.Cita.estado == "confirmada"
        ).first()

        if ocupada:
            raise HTTPException(
                status_code=400, 
                detail=f"El horario {s.hora} del día {s.fecha} ya no está disponible."
            )

        nueva_cita = models.Cita(
            user_id=req.user_id,
            sucursal_id=req.sucursal_id,
            servicio_id=req.servicio_id,
            fecha=fecha_obj,
            hora=s.hora,
            monto=monto_por_sesion,
            estado="confirmada",
            semaforo_al_agendar=user.semaforo
        )
        db.add(nueva_cita)
        citas_creadas.append(nueva_cita)
        fechas_horas.append({"fecha": s.fecha, "hora": s.hora})

    if es_rehabilitacion:
        user.sesiones_restantes = max(0, user.sesiones_restantes - cant_sesiones)

    db.commit()
    db.refresh(user)

    background_tasks.add_task(
        send_appointment_confirmation_email,
        email=user.email,
        nombre_paciente=f"{user.first_name} {user.last_name}",
        servicio=servicio.nombre,
        sucursal=sucursal.nombre,
        direccion=sucursal.direccion,
        fechas_horas=fechas_horas
    )

    mensaje_encoded = urllib.parse.quote("Listo reserve mi cita")
    whatsapp_link = f"https://wa.me/{WHATSAPP_FISIOTECUIDA}?text={mensaje_encoded}"

    return {
        "message": f"Se agendaron con éxito {len(citas_creadas)} sesiones.",
        "sesiones_restantes_actuales": user.sesiones_restantes,
        "whatsapp_url": whatsapp_link
    }

# --- CONFIRMAR CITA POR WHATSAPP ---
@app.post("/api/whatsapp/confirmar-cita")
@app.post("/whatsapp/confirmar-cita")
def confirmar_cita_whatsapp(req: schemas.ConfirmarWhatsAppSchema, db: Session = Depends(get_db)):
    cita = db.query(models.Cita).options(
        joinedload(models.Cita.servicio),
        joinedload(models.Cita.sucursal),
        joinedload(models.Cita.usuario)
    ).filter(models.Cita.id == req.cita_id).first()

    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada.")

    nombre_usuario = f"{cita.usuario.first_name} {cita.usuario.last_name}" if cita.usuario else "Cliente"
    servicio_nombre = cita.servicio.nombre if cita.servicio else "Consulta"
    sucursal_nombre = cita.sucursal.nombre if cita.sucursal else "Sucursal Tacuba"

    mensaje = (
        f"Hola, confirmando mi cita:\n"
        f"*Paciente:* {nombre_usuario}\n"
        f"*Servicio:* {servicio_nombre}\n"
        f"*Sucursal:* {sucursal_nombre}\n"
        f"*Fecha:* {cita.fecha}\n"
        f"*Hora:* {cita.hora}"
    )

    mensaje_encoded = urllib.parse.quote(mensaje)
    whatsapp_link = f"https://wa.me/{WHATSAPP_FISIOTECUIDA}?text={mensaje_encoded}"

    return {
        "message": "Enlace de WhatsApp generado correctamente.",
        "whatsapp_url": whatsapp_link
    }

def reagendar_cita_validada(cita_id: int, req: schemas.ReprogramarCitaSchema, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    
    cita = db.query(models.Cita).filter(models.Cita.id == cita_id).first()
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada.")

    # ✅ حماية الصلاحيات
    if current_user.role != "admin" and current_user.sucursal_id != cita.sucursal_id:
        raise HTTPException(status_code=403, detail="No tienes permiso para reagendar citas de otra sucursal")

    try:
        nueva_fecha = datetime.strptime(req.fecha, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido.")

    cita_existente = db.query(models.Cita).filter(
        models.Cita.sucursal_id == cita.sucursal_id,
        models.Cita.fecha == nueva_fecha,
        models.Cita.hora == req.hora,
        models.Cita.estado == "confirmada",
        models.Cita.id != cita_id
    ).first()

    if cita_existente:
        raise HTTPException(status_code=400, detail="El horario seleccionado ya no está disponible.")
    # =====================================================================
# تسجيل الحضور والغياب (Fase 2 - Asistencia)
# =====================================================================
@app.put("/api/citas/{cita_id}/asistencia")
@app.put("/citas/{cita_id}/asistencia")
def registrar_asistencia(
    cita_id: int, 
    asistio: bool, # True = حضر، False = غاب
    db: Session = Depends(get_db), 
    current_user: models.User = Depends(get_current_user)
):
    # 1. جلب الحجز
    cita = db.query(models.Cita).filter(models.Cita.id == cita_id).first()
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada")

    # 2. التأكد من الصلاحية (دكتور أو مدير)
    if current_user.role not in ["admin", "encargado", "fisioterapeuta"]:
        raise HTTPException(status_code=403, detail="No tienes permiso para registrar asistencia")

    # 3. التأكد من الفرع
    if current_user.role != "admin" and current_user.sucursal_id != cita.sucursal_id:
        raise HTTPException(status_code=403, detail="No puedes registrar asistencia de otra sucursal")

    # 4. التأكد إن الحضور متسجلش قبل كده
    if cita.asistio is not None:
        raise HTTPException(status_code=400, detail="La asistencia ya fue registrada previamente")

    # 5. تحديث الحالة
    cita.asistio = asistio
    
    if asistio:
        cita.estado = "completada"
        # خصم جلسة من رصيد المريض
        paciente = db.query(models.User).filter(models.User.id == cita.user_id).first()
        if paciente and paciente.sesiones_restantes > 0:
            paciente.sesiones_restantes -= 1
    else:
        cita.estado = "no_asistio"

    db.commit()

    # 6. تسجيل الحركة
    log_audit(db, current_user.id, "REGISTRAR_ASISTENCIA", f"Asistencia de cita {cita.id} registrada como {asistio}")

    return {"message": f"Asistencia registrada. El paciente {'asistió' if asistio else 'no asistió'}."}


# شكل البيانات اللي جاية من الفرونت إند
class ReagendarRequest(BaseModel):
    fecha: str
    hora: str

# الدالة اللي مسؤولة عن إعادة الجدولة
@app.put("/api/citas/{cita_id}/reagendar")
@app.put("/citas/{cita_id}/reagendar")
def reagendar_cita(cita_id: int, req: ReagendarRequest, db: Session = Depends(get_db)):
    
    # 1. البحث عن الموعد
    cita = db.query(models.Cita).filter(models.Cita.id == cita_id).first()
    
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada.")

    # 2. التعديلات اللي إنت شفتها فوق
    cita.fecha = req.fecha
    cita.hora = req.hora
    cita.estado = "confirmada"

    # 3. الحفظ
    db.commit()
    
    return {"message": "Cita reagendada exitosamente."}

@app.delete("/api/citas/{cita_id}/cancelar")
@app.delete("/citas/{cita_id}/cancelar")
def cancelar_cita(cita_id: int, db: Session = Depends(get_db)):
    cita = db.query(models.Cita).filter(models.Cita.id == cita_id).first()
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada.")

    if cita.estado == "cancelada":
        raise HTTPException(status_code=400, detail="La cita ya está cancelada.")

    cita.estado = "cancelada"
    
    user = db.query(models.User).filter(models.User.id == cita.user_id).first()
    if user and cita.servicio_id == 4:
        user.sesiones_restantes += 1

    db.commit()
    return {"message": "Cita cancelada con éxito."}

# --- RECUPERACIÓN DE CONTRASEÑA ---
@app.post("/api/forgot-password")
@app.post("/forgot-password")
async def forgot_password(request_data: schemas.ForgotPasswordRequest, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == request_data.email).first()
    if not user:
        return {"message": "Si el correo está registrado, recibirás un enlace de recuperación."}

    reset_token = create_access_token(data={"sub": str(user.id), "type": "password_reset"}, expires_delta=timedelta(minutes=15))
    try:
        await send_reset_password_email(user.email, reset_token)
    except Exception as e:
        print(f"Error enviando correo de recuperación: {e}")
        raise HTTPException(status_code=500, detail="Ocurrió un error al enviar el correo.")

    return {"message": "Si el correo está registrado, recibirás un enlace de recuperación."}

@app.post("/api/reset-password")
@app.post("/reset-password")
def reset_password(data: schemas.ResetPasswordRequest, db: Session = Depends(get_db)):
    payload = verify_token(data.token)
    if not payload or payload.get("type") != "password_reset":
        raise HTTPException(status_code=400, detail="Token inválido o expirado.")

    user = db.query(models.User).filter(models.User.id == int(payload.get("sub"))).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    user.password_hash = hash_password(data.new_password)
    db.commit()
    return {"message": "Tu contraseña se ha actualizado correctamente."}

# --- ENDPOINTS PARA PANEL DE TRABAJADOR / FISIOTERAPEUTA ---

@app.post("/api/fisioterapeuta/asistencia/entrada")
def registrar_entrada_dashboard(datos: schemas.AsistenciaRequest, db: Session = Depends(get_db)):
    ahora_mx = now_mexico()
    hoy = ahora_mx.date()
    hora_actual = ahora_mx.strftime("%I:%M %p")

    asistencia = db.query(models.AsistenciaWorker).filter(
        models.AsistenciaWorker.worker_id == datos.worker_id,
        models.AsistenciaWorker.fecha >= datetime.combine(hoy, datetime.min.time()),
        models.AsistenciaWorker.fecha <= datetime.combine(hoy, datetime.max.time())
    ).first()

    if not asistencia:
        asistencia = models.AsistenciaWorker(
            worker_id=datos.worker_id,
            fecha=ahora_mx,
            hora_entrada=hora_actual
        )
        db.add(asistencia)
        db.commit()
        db.refresh(asistencia)

    return {
        "id": asistencia.id,
        "worker_id": asistencia.worker_id,
        "fecha": str(asistencia.fecha.date() if isinstance(asistencia.fecha, datetime) else asistencia.fecha),
        "hora_entrada": asistencia.hora_entrada,
        "hora_salida": asistencia.hora_salida
    }

@app.post("/api/fisioterapeuta/asistencia/salida")
def registrar_salida_dashboard(datos: schemas.AsistenciaRequest, db: Session = Depends(get_db)):
    ahora_mx = now_mexico()
    hoy = ahora_mx.date()
    hora_actual = me = ahora_mx.strftime("%I:%M %p")

    asistencia = db.query(models.AsistenciaWorker).filter(
        models.AsistenciaWorker.worker_id == datos.worker_id,
        models.AsistenciaWorker.fecha >= datetime.combine(hoy, datetime.min.time()),
        models.AsistenciaWorker.fecha <= datetime.combine(hoy, datetime.max.time())
    ).first()

    if not asistencia:
        raise HTTPException(status_code=404, detail="No hay registro de entrada para el día de hoy")

    asistencia.hora_salida = hora_actual
    db.commit()
    db.refresh(asistencia)

    return {
        "id": asistencia.id,
        "worker_id": asistencia.worker_id,
        "fecha": str(asistencia.fecha.date() if isinstance(asistencia.fecha, datetime) else asistencia.fecha),
        "hora_entrada": asistencia.hora_entrada,
        "hora_salida": asistencia.hora_salida
    }

@app.get("/api/fisioterapeuta/citas", response_model=List[schemas.CitaDetalladaResponse])
def get_citas_fisioterapeuta(fecha: Optional[str] = None, db: Session = Depends(get_db)):
    query = db.query(models.Cita).options(
        joinedload(models.Cita.usuario),
        joinedload(models.Cita.sucursal),
        joinedload(models.Cita.servicio)
    )
    
    if fecha:
        try:
            fecha_dt = datetime.strptime(fecha, "%Y-%m-%d").date()
            query = query.filter(models.Cita.fecha == fecha_dt)
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato de fecha YYYY-MM-DD inválido.")
    
    citas = query.filter(models.Cita.servicio_id.isnot(None)).order_by(models.Cita.hora.asc()).all()
    return [c for c in citas if c.servicio is not None]

@app.put("/api/fisioterapeuta/citas/{cita_id}/asistencia")
def actualizar_asistencia(
    cita_id: int, 
    attended: Optional[bool] = None, 
    asistio: Optional[bool] = None,
    body: Optional[schemas.CitaCheckInRequest] = None,
    db: Session = Depends(get_db)
):
    cita = db.query(models.Cita).filter(models.Cita.id == cita_id).first()
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada.")

    estado_asistencia = True
    if attended is not None:
        estado_asistencia = attended
    elif asistio is not None:
        estado_asistencia = asistio
    elif body:
        if body.attended is not None:
            estado_asistencia = body.attended
        elif body.asistio is not None:
            estado_asistencia = body.asistio

    if hasattr(cita, "asistio"):
        cita.asistio = estado_asistencia
    if hasattr(cita, "atendida"):
        cita.atendida = estado_asistencia

    db.commit()
    db.refresh(cita)
    
    valor_final = getattr(cita, "asistio", getattr(cita, "atendida", estado_asistencia))
    
    return {
        "message": "Estado de asistencia actualizado correctamente.",
        "cita_id": cita.id,
        "asistio": valor_final,
        "atendida": valor_final
    }

@app.put("/api/fisioterapeuta/expediente/{cita_id}")
def actualizar_expediente(cita_id: int, data: schemas.FichaClinicaUpdate, db: Session = Depends(get_db)):
    cita = db.query(models.Cita).filter(models.Cita.id == cita_id).first()
    if not cita:
        raise HTTPException(status_code=404, detail="Cita no encontrada.")

    user = db.query(models.User).filter(models.User.id == cita.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Paciente no encontrado.")

    notas_texto = data.notes or data.notas_clinicas
    if notas_texto is not None:
        if hasattr(cita, "notas_clinicas"):
            cita.notas_clinicas = notas_texto
        if hasattr(cita, "notas"):
            cita.notas = notas_texto

    if data.semaforo:
        user.semaforo = data.semaforo
        cita.semaforo_al_agendar = data.semaforo

    sesiones_val = data.assigned_sessions if data.assigned_sessions is not None else data.sesiones_asignadas
    if sesiones_val is not None:
        user.sesiones_restantes = int(sesiones_val)

    db.commit()
    db.refresh(cita)
    db.refresh(user)

    notas_guardadas = getattr(cita, "notas_clinicas", getattr(cita, "notas", ""))

    return {
        "message": "Expediente y semáforo actualizados exitosamente.",
        "user_id": user.id,
        "nuevo_semaforo": user.semaforo,
        "sesiones_restantes": user.sesiones_restantes,
        "notas": notas_guardadas
    }

ALLOWED_WORKER_EMAILS = ["fisioterapeuta@clinica.com", "admin@clinica.com"]

@app.post("/api/fisioterapeuta/registro")
@app.post("/api/trabajador/registro-verificar")
async def verificar_registro_trabajador(data: schemas.WorkerRegisterCheck, db: Session = Depends(get_db)):
    email_clean = data.email.lower().strip()
    
    worker = db.query(models.Worker).filter(models.Worker.email == email_clean).first()
    
    if not worker:
        raise HTTPException(
            status_code=403, 
            detail="Acceso denegado: Este correo no está registrado como trabajador en la base de datos."
        )

    nombre_trabajador = getattr(data, 'name', None) or getattr(data, 'nombre', '')
    username_generado = nombre_trabajador.lower().strip().replace(" ", ".")
    
    worker.nombre = nombre_trabajador.strip()
    worker.username = username_generado
    db.commit()
    db.refresh(worker)

    try:
        await send_worker_username_email(worker.email, worker.username)
    except Exception as e:
        print(f"Error enviando correo de usuario: {e}")

    return {
        "message": "¡Correo verificado con éxito! Te hemos enviado tu usuario por correo.",
        "username": worker.username
    }

@app.post("/api/fisioterapeuta/check-in")
@app.post("/api/trabajador/checkin")
async def registrar_entrada_trabajador(data: schemas.WorkerCheckInRequest, db: Session = Depends(get_db)):
    username_input = data.username.strip()
    
    if not username_input:
        raise HTTPException(status_code=400, detail="Debes ingresar tu usuario asignado.")

    worker = db.query(models.Worker).filter(models.Worker.username == username_input).first()
    
    if not worker:
        raise HTTPException(
            status_code=404, 
            detail="El usuario ingresado no existe en la base de datos de trabajadores."
        )

    if not worker.is_active:
        raise HTTPException(status_code=403, detail="Esta cuenta de trabajador se encuentra inactiva.")

    codigo_acceso = generar_password(8)
    worker.password_hash = hash_password(codigo_acceso)
    
    ahora_mx = now_mexico()
    hora_entrada = me = ahora_mx.strftime("%I:%M %p")

  # =====================================================================
# مسارات العمال (Worker)
# =====================================================================
@app.post("/api/fisioterapeuta/login")
@app.post("/api/trabajador/login")
def login_trabajador(data: schemas.WorkerVerifyPasswordRequest, db: Session = Depends(get_db)):
    if not data.password.strip():
        raise HTTPException(status_code=400, detail="Debes ingresar la contraseña recibida por correo.")

    worker = db.query(models.Worker).filter(models.Worker.username == data.username.strip()).first()
    if not worker:
        raise HTTPException(status_code=404, detail="Trabajador no encontrado.")

    access_token = create_access_token(
        data={"sub": worker.username, "role": "worker"}
    )

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "worker": {
            "id": worker.id,
            "username": worker.username,
            "name": worker.nombre,
            "email": worker.email,
            "role": "worker"
        }
    }

@app.post("/api/fisioterapeuta/check-out")
@app.post("/api/trabajador/checkout")
def registrar_salida_trabajador(data: schemas.WorkerCheckInRequest, db: Session = Depends(get_db)):
    worker = db.query(models.Worker).filter(models.Worker.username == data.username.strip()).first()
    if not worker:
        raise HTTPException(status_code=404, detail="El usuario no existe.")

    ahora_mx = now_mexico()
    hora_salida_str = ahora_mx.strftime("%I:%M %p")

    if hasattr(models, 'AsistenciaWorker'):
        asistencia = db.query(models.AsistenciaWorker)\
            .filter(
                models.AsistenciaWorker.worker_id == worker.id,
                (models.AsistenciaWorker.hora_salida == None) | (models.AsistenciaWorker.hora_salida == "")
            )\
            .order_by(models.AsistenciaWorker.id.desc())\
            .first()

        if asistencia:
            asistencia.hora_salida = hora_salida_str
        else:
            asistencia = models.AsistenciaWorker(
                worker_id=worker.id,
                fecha=ahora_mx,
                hora_entrada="N/A",
                hora_salida=hora_salida_str
            )
            db.add(asistencia)

        db.commit()
        db.refresh(asistencia)

    return {
        "message": f"Salida registrada a las {hora_salida_str}.",
        "clock_out_time": hora_salida_str,
        "clockOutTime": hora_salida_str,
        "hora_salida": hora_salida_str,
        "horaSalida": hora_salida_str
    }

@app.get("/api/fisioterapeuta/asistencias")
def obtener_historial_asistencias(db: Session = Depends(get_db)):
    if not hasattr(models, 'AsistenciaWorker'):
        return []

    registros = db.query(models.AsistenciaWorker)\
        .options(joinedload(models.AsistenciaWorker.worker))\
        .order_by(models.AsistenciaWorker.id.desc())\
        .all()

    return [
        {
            "id": r.id,
            "trabajador": r.worker.nombre if (r.worker and r.worker.nombre) else "Desconocido",
            "username": r.worker.username if r.worker else "",
            "fecha": r.fecha.strftime("%Y-%m-%d") if (hasattr(r, 'fecha') and r.fecha) else now_mexico().strftime("%Y-%m-%d"),
            "hora_entrada": r.hora_entrada,
            "hora_salida": r.hora_salida if r.hora_salida else "En turno",
            "horaEntrada": r.hora_entrada,
            "horaSalida": r.hora_salida if r.hora_salida else "En turno",
            "clockInTime": r.hora_entrada,
            "clockOutTime": r.hora_salida if r.hora_salida else "En turno"
        }
        for r in registros
    ]


# =====================================================================
# مسار تسجيل الدخول بجوجل (Google Auth)
# =====================================================================
@app.post("/api/auth/google")
@app.post("/auth/google")
async def google_auth(data: dict, db: Session = Depends(get_db)):
    token = data.get("token") or data.get("credential")

    if not token:
        raise HTTPException(status_code=400, detail="Token de Google requerido")

    try:
        idinfo = id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            "572136890863-o8v9s5ium02dj02rsp7nojoabag0fdg0.apps.googleusercontent.com"
        )

        email = idinfo.get("email")
        given_name = idinfo.get("given_name") or ""
        family_name = idinfo.get("family_name") or ""

        if not email:
            raise HTTPException(status_code=400, detail="Email no encontrado en el token")

        # ✅ 1. البحث عن المستخدم
        user = db.query(models.User).filter(models.User.email == email).first()

        es_nuevo = False

        # ✅ 2. إذا لم يوجد → إنشاء حساب جديد تلقائياً
        if not user:
            # قيم افتراضية للحقول الإجبارية التي لا تأتي من Google
            birth_date_default = date(2000, 1, 1)

            user = models.User(
                first_name=(given_name or "Usuario")[:50],
                last_name=(family_name or "Google")[:50],
                email=email,
                password_hash=hash_password(secrets.token_urlsafe(32)),  # كلمة مرور عشوائية غير معروفة
                encrypted_phone=encrypt_data("0000000000"),               # هاتف وهمي (يمكن تعديله لاحقاً)
                country_code="+52",
                birth_date=birth_date_default,
                role="client",
                is_active=True,              # ✅ مفعّل مباشرة (Google أثبت بريده)
                semaforo="ninguno",
                sesiones_restantes=0
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            es_nuevo = True
            log_audit(db, user.id, "REGISTER_GOOGLE", f"Registro automático vía Google: {email}")

        # ✅ 3. إذا وُجد لكن غير مفعّل → فعّله (Google أثبت بريده)
        elif not user.is_active:
            user.is_active = True
            db.commit()
            db.refresh(user)

        # ✅ 4. إنشاء التوكن وإرجاع بيانات المستخدم
        access_token = create_access_token(data={"sub": str(user.id), "role": user.role})
        log_audit(db, user.id, "LOGIN_GOOGLE", f"Inicio de sesión con Google: {email}")

        return {
            "access_token": access_token,
            "token_type": "bearer",
            "is_new_user": es_nuevo,
            "user": {
                "id": user.id,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "role": user.role,
                "semaforo": user.semaforo,
                "sesiones_restantes": user.sesiones_restantes
            }
        }

    except ValueError as e:
        print(f"Error validando token: {e}")
        raise HTTPException(status_code=401, detail="Token de Google inválido")


# =====================================================================
# إغلاق الأجندة (Fase 2 - Bloqueos)
# =====================================================================
@app.post("/api/agenda/bloquear", status_code=status.HTTP_201_CREATED)
@app.post("/agenda/bloquear", status_code=status.HTTP_201_CREATED)
def bloquear_agenda(
    req: schemas.BloqueoAgendaSchema,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user)
):
    if current_user.role not in ["admin", "encargado", "fisioterapeuta"]:
        raise HTTPException(status_code=403, detail="No tienes permiso para bloquear la agenda")

    if current_user.role != "admin" and current_user.sucursal_id != req.sucursal_id:
        raise HTTPException(status_code=403, detail="No puedes bloquear la agenda de otra sucursal")

    nuevo_bloqueo = models.EventoAgenda(
        profesional_id=current_user.id,
        sucursal_id=req.sucursal_id,
        fecha=req.fecha,
        hora_inicio=req.hora_inicio,
        hora_fin=req.hora_fin,
        motivo=req.motivo
    )
    
    db.add(nuevo_bloqueo)
    db.commit()
    db.refresh(nuevo_bloqueo)
    log_audit(db, current_user.id, "BLOQUEAR_AGENDA", f"Bloqueó el día {req.fecha} de {req.hora_inicio} a {req.hora_fin}")

    return {"message": "Agenda bloqueada correctamente", "id": nuevo_bloqueo.id}


# =====================================================================
# مسار جلب قائمة المرضى (Fase 1 & 3)
# =====================================================================
@app.get("/api/pacientes")
@app.get("/pacientes")
def get_pacientes(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.role not in ["admin", "encargado", "fisioterapeuta"]:
        raise HTTPException(status_code=403, detail="No tienes permiso para ver pacientes")

    query = db.query(models.User).filter(models.User.role == "client")
    if current_user.role != "admin":
        query = query.filter(models.User.sucursal_id == current_user.sucursal_id)

    pacientes = query.all()

 # =====================================================================
# مسار جلب قائمة المرضى (Fase 1 & 3)
# =====================================================================
@app.get("/api/pacientes")
@app.get("/pacientes")
def get_pacientes(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.role not in ["admin", "encargado", "fisioterapeuta"]:
        raise HTTPException(status_code=403, detail="No tienes permiso para ver pacientes")

    query = db.query(models.User).filter(models.User.role == "client")
    if current_user.role != "admin":
        query = query.filter(models.User.sucursal_id == current_user.sucursal_id)

    pacientes = query.all()

    resultado = []
    for p in pacientes:
        try:
            telefono = p.phone
            if telefono == "[Error al desencriptar]":
                telefono = "No disponible"
        except Exception:
            telefono = "No disponible"

        resultado.append({
            "id": p.id,
            "nombre": f"{p.first_name} {p.last_name}",
            "email": p.email,
            "telefono": telefono,
            "semaforo": p.semaforo
        })

    return resultado


# =====================================================================
# مسار حفظ السجل الطبي (Fase 3)
# =====================================================================
@app.post("/api/expedientes/{patient_id}")
@app.post("/expedientes/{patient_id}")
def guardar_expediente(patient_id: int, data: dict, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    if current_user.role not in ["admin", "encargado", "fisioterapeuta"]:
        raise HTTPException(status_code=403, detail="No tienes permiso")

    expediente = db.query(models.HistoriaClinica).filter(models.HistoriaClinica.patient_id == patient_id).first()
    if not expediente:
        expediente = models.HistoriaClinica(patient_id=patient_id)
        db.add(expediente)
    if "datos_personales" in data:
        expediente.datos_personales = data["datos_personales"]
        if "antecedentes_familiares" in data:expediente.antecedentes_familiares = data["antecedentes_familiares"]
        if "antecedentes_personales" in data:
            expediente.antecedentes_personales = data["antecedentes_personales"]
    if "habitos" in data:expediente.habitos = data["habitos"]
    if "notas_soap" in data: 
        expediente.notas_soap = data["notas_soap"]

    db.commit()
    db.refresh(expediente)
    return {"message": "Expediente guardado correctamente"}
@app.get("/api/expedientes/{patient_id}")
@app.get("/expedientes/{patient_id}")
def obtener_expediente(patient_id: int, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    
    if current_user.role not in ["admin", "encargado", "fisioterapeuta"]:
        raise HTTPException(status_code=403, detail="No tienes permiso")
    
    expediente = db.query(models.HistoriaClinica).filter(models.HistoriaClinica.patient_id == patient_id).first()
    
    if not expediente:
        raise HTTPException(status_code=404, detail="No se encontró expediente para este paciente")
        
    return {
        "patient_id": expediente.patient_id,
        "datos_personales": expediente.datos_personales,
        "antecedentes_familiares": getattr(expediente, 'antecedentes_familiares', {}),
        "antecedentes_personales": getattr(expediente, 'antecedentes_personales', {}),
        "habitos": getattr(expediente, 'habitos', {}),
        "notas_soap": expediente.notas_soap
    }
@app.get("/api/citas")
@app.get("/citas")
def get_citas(db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    # التأكد إن اللي بيطلب الداتا ده فيزيو أو أدمن
    if current_user.role not in ["admin", "encargado", "fisioterapeuta"]:
        raise HTTPException(status_code=403, detail="No tienes permiso")
    
    # جلب كل الحجوزات من الداتابيز
    citas = db.query(models.Cita).all()
    
    resultado = []
    for cita in citas:
        # تحديد الوردية (صبح ولا مساء) بناءً على الساعة
        try:
            hora_int = int(cita.hora.split(":")[0])
            turno = "Mañana" if hora_int < 12 else "Tarde"
        except:
            turno = "Mañana"

        resultado.append({
            "id": cita.id,
            "user_id": cita.user_id,
            "paciente": f"{cita.usuario.first_name} {cita.usuario.last_name}" if cita.usuario else f"Paciente #{cita.user_id}",
            "hora": cita.hora,
            "servicio": cita.servicio.nombre if cita.servicio else "Consulta",
            "estado": "Asistió" if cita.asistio else "Pendiente",
            "turno": turno
        })
        
    return resultado 

     