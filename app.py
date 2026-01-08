import pandas as pd
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# --- CONFIGURACIÓN DE CORREO ---
EMAIL_DESTINO = "ctejas@metramar.es"
EMAIL_ORIGEN = "ctmetramar@gmail.com"
EMAIL_PASSWORD = "jdos huud izis niqp"  # Tu contraseña de aplicación
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# --- CONFIGURACIÓN DE ARCHIVOS ---
ERP_FILE = "VencimientosXXX.xls"   
MASTER_FILE = "vencimientos.xlsx"   
LOG_FILE = "log_actualizacion.txt"

def actualizar_y_enviar():
    log_mensaje = [] # Lista para guardar las líneas del log y enviarlas por mail
    
    print("--- Iniciando proceso de actualización ---")
    
    # 1. Cargar datos
    try:
        # Intentamos cargar con xlrd (para .xls antiguos)
        erp_df = pd.read_excel(ERP_FILE, dtype=str, engine='xlrd')
    except ImportError:
        print("Aviso: Motor 'xlrd' no encontrado o fallo, intentando carga estándar.")
        erp_df = pd.read_excel(ERP_FILE, dtype=str)
    except FileNotFoundError:
        print(f"ERROR CRÍTICO: No se encuentra el archivo {ERP_FILE}")
        return

    try:
        master_df = pd.read_excel(MASTER_FILE, dtype=str)
    except FileNotFoundError:
        print(f"ERROR CRÍTICO: No se encuentra el archivo {MASTER_FILE}")
        return

    # 2. Normalizar
    erp_df.columns = erp_df.columns.str.strip().str.upper()
    master_df.columns = master_df.columns.str.strip().str.upper()

    KEY = "VEHICULO"
    COL_FECHA = "FECHA DE VENCIN"

    # 3. Fechas
    erp_df[COL_FECHA] = pd.to_datetime(erp_df[COL_FECHA], errors="coerce")
    master_df[COL_FECHA] = pd.to_datetime(master_df[COL_FECHA], errors="coerce")

    # 4. Merge
    merged_df = pd.merge(
        master_df,
        erp_df[[KEY, COL_FECHA]],
        on=KEY,
        how="outer",
        suffixes=("_old", "_new")
    )

    # 5. Generar Log y Contenido del Email
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    header_msg = f"=== Actualización {timestamp} ==="
    log_mensaje.append(header_msg)
    
    # Abrimos el archivo log para escribir (histórico)
    with open(LOG_FILE, "a", encoding="utf-8") as f_log:
        f_log.write(f"\n{header_msg}\n")

        # Vehículos nuevos
        nuevos = merged_df[merged_df[f"{COL_FECHA}_old"].isna() & merged_df[f"{COL_FECHA}_new"].notna()]
        if not nuevos.empty:
            log_mensaje.append(f"\nDetectados {len(nuevos)} vehículos nuevos:")
            for _, row in nuevos.iterrows():
                fecha = row[f'{COL_FECHA}_new'].date() if pd.notna(row[f'{COL_FECHA}_new']) else "N/A"
                msg = f"➕ Nuevo: {row[KEY]} - Vence: {fecha}"
                log_mensaje.append(msg)
                f_log.write(msg + "\n")
        else:
            log_mensaje.append("No hay vehículos nuevos.")

        # Vehículos actualizados
        actualizados = merged_df[
            merged_df[f"{COL_FECHA}_old"].notna() &
            merged_df[f"{COL_FECHA}_new"].notna() &
            (merged_df[f"{COL_FECHA}_old"] != merged_df[f"{COL_FECHA}_new"])
        ]
        if not actualizados.empty:
            log_mensaje.append(f"\nDetectados {len(actualizados)} cambios de fecha:")
            for _, row in actualizados.iterrows():
                f_old = row[f'{COL_FECHA}_old'].date()
                f_new = row[f'{COL_FECHA}_new'].date()
                msg = f"✏️ Actualizado {row[KEY]}: {f_old} → {f_new}"
                log_mensaje.append(msg)
                f_log.write(msg + "\n")
        else:
            log_mensaje.append("No hay actualizaciones de fechas existentes.")

    # 6. Consolidar y Guardar Excel
    merged_df[COL_FECHA] = merged_df[f"{COL_FECHA}_new"].combine_first(merged_df[f"{COL_FECHA}_old"])
    final_df = merged_df[[KEY, COL_FECHA]].copy()
    final_df.to_excel(MASTER_FILE, index=False)
    print(f"✅ Fichero maestro actualizado: {MASTER_FILE}")

    # 7. ENVIAR EMAIL
    body_email = "\n".join(log_mensaje)
    
    try:
        msg = MIMEMultipart()
        msg['From'] = EMAIL_ORIGEN
        msg['To'] = EMAIL_DESTINO
        msg['Subject'] = f"Reporte Vencimientos - {timestamp}"

        msg.attach(MIMEText(body_email, 'plain'))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_ORIGEN, EMAIL_PASSWORD)
        text = msg.as_string()
        server.sendmail(EMAIL_ORIGEN, EMAIL_DESTINO, text)
        server.quit()
        print("📧 Email enviado correctamente.")
        
    except Exception as e:
        print(f"❌ Error al enviar email: {e}")

# Ejecutar
if __name__ == "__main__":
    actualizar_y_enviar()

