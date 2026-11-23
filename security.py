import os
import bcrypt
from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv()

# --- CLAVE DE ENCRIPCIÓN DE DATOS SENSIBLES ---
# Se utiliza una clave estática o de entorno para no invalidar los datos guardados al reiniciar la App
SECRET_ENCRYPTION_KEY = os.getenv("DB_ENCRYPTION_KEY")
if not SECRET_ENCRYPTION_KEY:
    # Key por defecto solo para desarrollo local si no existe en .env
    SECRET_ENCRYPTION_KEY = Fernet.generate_key().decode()

# Asegura que la clave esté codificada correctamente como bytes de Fernet
if isinstance(SECRET_ENCRYPTION_KEY, str):
    SECRET_ENCRYPTION_KEY_BYTES = SECRET_ENCRYPTION_KEY.encode()
else:
    SECRET_ENCRYPTION_KEY_BYTES = SECRET_ENCRYPTION_KEY

fernet = Fernet(SECRET_ENCRYPTION_KEY_BYTES)


# --- FUNCIONES DE CONTRASEÑA (BCRYPT DIRECTO) ---
def hash_password(password: str) -> str:
    """
    Hashea la contraseña usando la librería bcrypt directa.
    Trunca a 72 bytes para evitar el ValueError nativo de bcrypt.
    """
    pwd_bytes = password.encode('utf-8')[:72]
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Compara la contraseña plana con el hash guardado usando bcrypt directo."""
    try:
        pwd_bytes = plain_password.encode('utf-8')[:72]
        hash_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    except Exception as e:
        print(f"Error al verificar la contraseña: {e}")
        return False


# --- FUNCIONES DE ENCRIPCIÓN DE DATOS SENSIBLES (PII) ---
def encrypt_data(data: str) -> str:
    """Encripta texto sensible (ej. Teléfono) antes de guardarlo en la BDD."""
    if not data:
        return data
    return fernet.encrypt(data.encode('utf-8')).decode('utf-8')

def decrypt_data(encrypted_data: str) -> str:
    """Desencripta los datos al leerlos de la BDD para enviarlos al cliente."""
    if not encrypted_data:
        return encrypted_data
    try:
        return fernet.decrypt(encrypted_data.encode('utf-8')).decode('utf-8')
    except Exception:
        return "[Error al desencriptar]"


# --- CONFIGURACIÓN Y FUNCIONES JWT ---
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "CLAVE_SECRETA_PARA_JWT_CAMBIAME")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))

def create_access_token(data: dict) -> str:
    """Crea un token JWT con fecha de expiración."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str):
    """Verifica si el token es válido y no ha expirado."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None