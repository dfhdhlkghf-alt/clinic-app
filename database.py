import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Cargar variables del archivo .env
load_dotenv()

# Credenciales por defecto para entorno local
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_NAME = os.getenv("DB_NAME", "fisiotcuida_db")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "DinoCag0n.310604")
DB_PORT = os.getenv("DB_PORT", "5432")
DATABASE_URL = "postgresql://fisio_db_zyys_user:B6ZamaHCmrCKL0IhIadPXIH2Ie2cjTj5adpg-do2ph1e8bjmc738d2k4g-a/fisio_db_zyys"
# Prioridad 1: Obtener la URL completa del .env o de Render

# Prioridad 2: Si no existe DATABASE_URL, construirla con los datos locales de PostgreSQL
if not DATABASE_URL:
    DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# Corrección de protocolo por compatibilidad con versiones de SQLAlchemy/Postgres
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
