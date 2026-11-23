import os
from dotenv import load_dotenv
from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType

load_dotenv()

MAIL_USERNAME = os.getenv("MAIL_USERNAME", "ejemplo@gmail.com")
MAIL_PASSWORD = os.getenv("MAIL_PASSWORD", "secret")
MAIL_FROM = os.getenv("MAIL_FROM", "ejemplo@gmail.com")
MAIL_PORT = int(os.getenv("MAIL_PORT", 465))
MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
# Aseguramos eliminar barras diagonales al final si las hay
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")

conf = ConnectionConfig(
    MAIL_USERNAME=MAIL_USERNAME,
    MAIL_PASSWORD=MAIL_PASSWORD,
    MAIL_FROM=MAIL_FROM,
    MAIL_PORT=MAIL_PORT,
    MAIL_SERVER=MAIL_SERVER,
    MAIL_STARTTLS=False,
    MAIL_SSL_TLS=True,
    USE_CREDENTIALS=True
)

MAPS_URLS = {
    "Tacuba": "https://maps.app.goo.gl/doZyuSxFgogqZm7UA",
    "Camarones": "https://maps.app.goo.gl/VRSf3ba3iro7Hn8W6"
}

async def send_activation_email(email: str, token: str):
    activation_link = f"{FRONTEND_URL}/activar-cuenta?token={token}"
    html_content = f"""
    <div style="font-family: Arial, sans-serif; padding: 20px; background-color: #f4f4f4;">
        <div style="max-width: 500px; margin: auto; background: white; padding: 20px; border-radius: 8px;">
            <h2 style="color: #009EE3;">¡Bienvenido a Fisio Tecuida!</h2>
            <p>Gracias por registrarte. Para activar tu cuenta y agendar tus citas, haz clic en el siguiente botón:</p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{activation_link}" style="background-color: #009EE3; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
                    Activar mi cuenta
                </a>
            </div>
        </div>
    </div>
    """
    message = MessageSchema(
        subject="Activación de Cuenta - Fisio Tecuida",
        recipients=[email],
        body=html_content,
        subtype=MessageType.html
    )
    fm = FastMail(conf)
    await fm.send_message(message)

async def send_reset_password_email(email: str, token: str):
    reset_link = f"{FRONTEND_URL}/recuperar-password?token={token}"
    html_content = f"""
    <div style="font-family: Arial, sans-serif; padding: 20px; background-color: #f4f4f4;">
        <div style="max-width: 500px; margin: auto; background: white; padding: 20px; border-radius: 8px;">
            <h2 style="color: #009EE3;">Recuperación de Contraseña</h2>
            <p>Haz clic en el siguiente botón para elegir una nueva contraseña:</p>
            <div style="text-align: center; margin: 30px 0;">
                <a href="{reset_link}" style="background-color: #009EE3; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
                    Restablecer Contraseña
                </a>
            </div>
        </div>
    </div>
    """
    message = MessageSchema(
        subject="Recuperación de Contraseña - Fisio Tecuida",
        recipients=[email],
        body=html_content,
        subtype=MessageType.html
    )
    fm = FastMail(conf)
    await fm.send_message(message)

async def send_worker_passcode(email: str, code: str):
    html_content = f"""
    <div style="font-family: Arial, sans-serif; padding: 20px; background-color: #f4f4f4;">
        <div style="max-width: 500px; margin: auto; background: white; padding: 20px; border-radius: 8px;">
            <h2 style="color: #009EE3;">Acceso al Panel Fisioterapia</h2>
            <p>Tu código temporal para desbloquear el Dashboard hoy es:</p>
            <h1 style="text-align: center; color: #333; letter-spacing: 4px;">{code}</h1>
            <p style="font-size: 12px; color: #777;">Si no solicitaste este código, ignora este mensaje.</p>
        </div>
    </div>
    """
    message = MessageSchema(
        subject="Código de Acceso Fisioterapeuta - Fisio Tecuida",
        recipients=[email],
        body=html_content,
        subtype=MessageType.html
    )
    fm = FastMail(conf)
    await fm.send_message(message)

async def send_worker_username_email(email: str, username: str):
    subject = "Tu usuario asignado - FisioTCuida"
    content = f"Hola, tu registro ha sido verificado. Tu nombre de usuario para ingresar es: {username}"
    message = MessageSchema(
        subject=subject,
        recipients=[email],
        body=content,
        subtype=MessageType.plain
    )
    fm = FastMail(conf)
    await fm.send_message(message)

async def send_appointment_confirmation_email(
    email: str, 
    nombre_paciente: str, 
    servicio: str, 
    sucursal: str, 
    direccion: str, 
    fechas_horas: list
):
    maps_url = MAPS_URLS.get(sucursal, f"https://maps.google.com/?q={direccion.replace(' ', '+')}")
    
    filas_citas = "".join([
        f"<tr><td style='padding: 8px; border-bottom: 1px solid #ddd;'>{item['fecha']}</td>"
        f"<td style='padding: 8px; border-bottom: 1px solid #ddd; text-align: right;'><strong>{item['hora']}</strong></td></tr>"
        for item in fechas_horas
    ])

    html_content = f"""
    <div style="font-family: Arial, sans-serif; background-color: #f4f4f4; padding: 20px;">
        <div style="max-width: 550px; margin: auto; background: white; padding: 25px; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,0.1);">
            <h2 style="color: #009EE3; text-align: center; margin-top: 0;">¡Cita Confirmada!</h2>
            <p>Hola <strong>{nombre_paciente}</strong>,</p>
            <p>Tu reservación en <strong>Fisio Tecuida</strong> ha sido registrada exitosamente.</p>
            
            <div style="background-color: #f8f9fa; border-left: 4px solid #009EE3; padding: 15px; margin: 20px 0;">
                <p style="margin: 5px 0;"><strong>Servicio:</strong> {servicio}</p>
                <p style="margin: 5px 0;"><strong>Sucursal:</strong> {sucursal}</p>
                <p style="margin: 5px 0;"><strong>Dirección:</strong> {direccion}</p>
                
                <div style="text-align: center; margin-top: 15px;">
                    <a href="{maps_url}" target="_blank" style="background-color: #28a745; color: white; padding: 10px 18px; text-decoration: none; border-radius: 5px; font-size: 14px; font-weight: bold; display: inline-block;">
                        📍 Abrir en Google Maps
                    </a>
                </div>
            </div>

            <h3 style="color: #333; font-size: 16px; margin-bottom: 10px;">Horario(s) Agendado(s):</h3>
            <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
                <thead>
                    <tr style="background-color: #e9ecef; text-align: left;">
                        <th style="padding: 8px;">Fecha</th>
                        <th style="padding: 8px; text-align: right;">Hora</th>
                    </tr>
                </thead>
                <tbody>
                    {filas_citas}
                </tbody>
            </table>

            <div style="background-color: #fff3cd; border: 1px solid #ffeeba; color: #856404; padding: 15px; border-radius: 5px; font-size: 13px;">
                <strong style="font-size: 14px;">⚠️ Instrucciones importantes para tu consulta:</strong>
                <ul style="margin: 8px 0 0 0; padding-left: 20px;">
                    <li><strong>Puntualidad:</strong> Te sugerimos llegar 10 minutos antes de tu hora programada.</li>
                    <li><strong>Tolerancia:</strong> Contamos con una tolerancia máxima de <strong>15 minutos</strong>. Después de este tiempo, la sesión no podrá realizarse para no afectar a otros pacientes.</li>
                    <li><strong>Vestimenta:</strong> Acude con ropa cómoda o deportiva que permita evaluar el área a tratar.</li>
                    <li><strong>Reagendar/Cancelar:</strong> Si necesitas realizar algún cambio, favor de realizarlo con anticipación desde la plataforma.</li>
                </ul>
            </div>

            <p style="font-size: 12px; color: #888; text-align: center; margin-top: 25px;">
                Este es un mensaje automático generado por Fisio Tecuida.
            </p>
        </div>
    </div>
    """

    message = MessageSchema(
        subject=f"Confirmación de Cita - Fisio Tecuida ({sucursal})",
        recipients=[email],
        body=html_content,
        subtype=MessageType.html
    )
    fm = FastMail(conf)
    await fm.send_message(message)