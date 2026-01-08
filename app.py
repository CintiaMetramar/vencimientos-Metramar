import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import smtplib
from email.mime.text import MIMEText
import urllib.parse
import io

# Configuración de página
st.set_page_config(page_title="Gestión Flota - Metramar", page_icon="🚛", layout="wide")

# ==========================================
# 🔐 1. SEGURIDAD (LOGIN)
# ==========================================
def check_password():
    """Protege la app con contraseña."""
    if "password" not in st.secrets:
        st.error("⚠️ Error: No has configurado la contraseña en los Secrets de Streamlit.")
        return False

    def password_entered():
        if st.session_state["password"] == st.secrets["password"]:
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("🔑 Contraseña:", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("🔑 Contraseña:", type="password", on_change=password_entered, key="password")
        st.error("❌ Contraseña incorrecta")
        return False
    else:
        return True

if not check_password():
    st.stop()

# ==========================================
# 📂 2. ZONA DE CARGA DE ARCHIVOS
# ==========================================
st.title("🚛 Centro de Control: Flota Metramar")
st.markdown("""
**Instrucciones:**
1. Arrastra tu **MAESTRO** actual (`vencimientos.xlsx`).
2. Arrastra el **SEMANAL** del ERP (`.xls` o `.xlsx`).
3. El sistema cruzará los datos, actualizará fechas, te dejará descargar el nuevo maestro y enviar el reporte.
""")

col1, col2 = st.columns(2)
with col1:
    uploaded_master = st.file_uploader("1️⃣ Sube el MAESTRO (.xlsx)", type=["xlsx"])
with col2:
    uploaded_weekly = st.file_uploader("2️⃣ Sube el SEMANAL del ERP (.xls o .xlsx)", type=["xls", "xlsx"])

# ⛔ STOP: Si no hay archivos, no hacemos nada (Evita errores de "fichero no encontrado")
if not uploaded_master or not uploaded_weekly:
    st.info("👋 Esperando archivos... Sube ambos para activar el sistema.")
    st.stop()

# ==========================================
# 🔄 3. LÓGICA DE FUSIÓN (CRUCE DE DATOS)
# ==========================================
st.divider()
st.write("🔄 **Procesando actualización...**")

try:
    # Leer Maestro
    df_master = pd.read_excel(uploaded_master, dtype=str)
    
    # Leer Semanal (detectando motor para .xls antiguo)
    if uploaded_weekly.name.endswith('.xls'):
        try:
            df_weekly = pd.read_excel(uploaded_weekly, dtype=str, engine='xlrd')
        except ImportError:
            st.error("⚠️ Falta la librería 'xlrd' en requirements.txt para leer archivos .xls antiguos.")
            st.stop()
    else:
        df_weekly = pd.read_excel(uploaded_weekly, dtype=str)

    # Normalizar cabeceras (Mayúsculas y sin espacios)
    df_master.columns = df_master.columns.str.strip().str.upper()
    df_weekly.columns = df_weekly.columns.str.strip().str.upper()

    # --- DETECCIÓN INTELIGENTE DE COLUMNAS ---
    # Buscamos la columna clave (Matrícula o Vehículo)
    KEY_M = next((c for c in df_master.columns if "MATRICULA" in c or "VEHICULO" in c or "VEHÍCULO" in c), None)
    KEY_W = next((c for c in df_weekly.columns if "MATRICULA" in c or "VEHICULO" in c or "VEHÍCULO" in c), None)
    
    # Buscamos la columna de Fechas
    DATE_M = next((c for c in df_master.columns if "VENCI" in c and "FECHA" in c), None)
    DATE_W = next((c for c in df_weekly.columns if "VENCI" in c and "FECHA" in c), None)

    if not KEY_M or not KEY_W or not DATE_M or not DATE_W:
        st.error(f"❌ No he podido identificar las columnas automáticamente. Revisa los encabezados de tus Excels.\nMaster: {df_master.columns.tolist()}\nSemanal: {df_weekly.columns.tolist()}")
        st.stop()

    # Estandarizamos para el cruce
    df_master = df_master.rename(columns={KEY_M: "MATRICULA_KEY"})
    df_weekly = df_weekly.rename(columns={KEY_W: "MATRICULA_KEY"})

    # Convertir Fechas a Datetime
    df_master[DATE_M] = pd.to_datetime(df_master[DATE_M], errors="coerce")
    df_weekly[DATE_W] = pd.to_datetime(df_weekly[DATE_W], errors="coerce")

    # --- EL CRUCE (MERGE) ---
    # Usamos LEFT JOIN para mantener tu estructura del Maestro intacta y solo actualizar datos
    merged = pd.merge(
        df_master,
        df_weekly[["MATRICULA_KEY", DATE_W]],
        on="MATRICULA_KEY",
        how="left",
        suffixes=("", "_new")
    )

    # Actualizar fechas: Si el ERP trae fecha nueva, la ponemos. Si no, dejamos la que había.
    merged[DATE_M] = merged[f"{DATE_W}_new"].combine_first(merged[DATE_M])
    
    # Limpieza
    df_final = merged.drop(columns=[f"{DATE_W}_new"], errors='ignore')

    # Preparar Descarga del Nuevo Maestro
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df_final.to_excel(writer, index=False)
    
    st.success("✅ ¡Datos actualizados correctamente!")
    
    # Botón para descargar el resultado
    st.download_button(
        label="💾 Descargar Maestro Actualizado (.xlsx)",
        data=buffer.getvalue(),
        file_name=f"vencimientos_actualizado_{datetime.now().strftime('%Y-%m-%d')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

except Exception as e:
    st.error(f"❌ Error técnico al procesar los archivos: {e}")
    st.stop()

# ==========================================
# 🚦 4. GENERACIÓN DEL REPORTE VISUAL
# ==========================================
st.divider()
st.subheader("📊 Informe de Estado")

hoy = datetime.now()
margen_30 = hoy + timedelta(days=30)
margen_menos_30 = hoy - timedelta(days=30)

# Filtro de fechas para el reporte
mask = (df_final[DATE_M] <= margen_30) & (df_final[DATE_M] >= margen_menos_30)
df_reporte = df_final[mask].copy()

if df_reporte.empty:
    st.success("✨ ¡Genial! No hay avisos pendientes en estas fechas.")
else:
    st.warning(f"⚠️ Se han detectado **{len(df_reporte)}** vehículos para revisar.")
    
    datos_email = []

    # Recorremos para pintar la tabla y preparar el email
    for _, row in df_reporte.iterrows():
        matricula = row["MATRICULA_KEY"]
        fecha = row[DATE_M]
        
        # Intentamos recuperar Conductor y Teléfono
        col_cond = next((c for c in df_final.columns if "CONDUCTOR" in c), None)
        col_tel = next((c for c in df_final.columns if "TELEFONO" in c or "TELÉFONO" in c), None)
        
        conductor = row[col_cond] if col_cond and pd.notna(row[col_cond]) else "Desconocido"
        telefono = str(row[col_tel]).replace(".0", "") if col_tel and pd.notna(row[col_tel]) else ""

        # Lógica del Semáforo
        if pd.isna(fecha):
            bola = "⚪"
            bg = "#f8f9fa"
        elif fecha < hoy:
            bola = "🔴"
            bg = "#ffe6e6" # Rojo
        elif fecha <= hoy + timedelta(days=7):
            bola = "🟡"
            bg = "#fff3cd" # Amarillo
        else:
            bola = "🟢"
            bg = "#d4edda" # Verde

        fecha_str = fecha.strftime('%d/%m/%Y') if pd.notna(fecha) else "S/F"

        # Generar Link WhatsApp
        tel_clean = "".join(filter(str.isdigit, telefono))
        if len(tel_clean) == 9: tel_clean = "34" + tel_clean
        
        link_wa = ""
        if len(tel_clean) >= 9:
            msg = f"Hola {conductor}, el vehículo {matricula} vence el {fecha_str}. Por favor revisa la documentación."
            link_wa = f"https://wa.me/{tel_clean}?text={urllib.parse.quote(msg)}"

        datos_email.append({
            "bola": bola, "matr": matricula, "cond": conductor, 
            "fecha": fecha_str, "bg": bg, "link": link_wa
        })

    # Mostrar tabla visual
    c1, c2, c3, c4, c5 = st.columns([0.5, 1.5, 2, 1.5, 1.5])
    c1.markdown("**Est.**")
    c2.markdown("**Matrícula**")
    c3.markdown("**Conductor**")
    c4.markdown("**Fecha**")
    c5.markdown("**Acción**")
    st.write("---")

    for d in datos_email:
        with st.container():
            c1, c2, c3, c4, c5 = st.columns([0.5, 1.5, 2, 1.5, 1.5])
            c1.write(d["bola"])
            c2.write(d["matr"])
            c3.write(d["cond"])
            c4.write(d["fecha"])
            if d["link"]:
                c5.link_button("📲 Chat", d["link"])
            else:
                c5.write("-")
            st.write("---")

    # ==========================================
    # 📧 5. ENVÍO DE EMAIL
    # ==========================================
    st.subheader("📩 Enviar Reporte por Email")
    
    if st.button("📤 Enviar Email Ahora"):
        with st.spinner("Conectando con Gmail..."):
            EMAIL_ORIGEN = "ctmetramar@gmail.com"
            EMAIL_DESTINO = "ctejas@metramar.es"
            EMAIL_PASS = st.secrets.get("EMAIL_PASSWORD", "")

            # Construcción HTML del correo
            filas_html = ""
            for d in datos_email:
                btn_html = ""
                if d['link']:
                    btn_html = f"""<a href="{d['link']}" style="background-color:#25D366; color:white; padding:4px 8px; text-decoration:none; border-radius:4px; font-size:12px;">📲 WhatsApp</a>"""
                else:
                    btn_html = "<span style='color:#ccc'>-</span>"

                filas_html += f"""
                <tr style="background-color:{d['bg']}; border-bottom:1px solid #ddd;">
                    <td style="text-align:center; font-size:18px; padding:8px;">{d['bola']}</td>
                    <td style="padding:8px;"><strong>{d['matr']}</strong></td>
                    <td style="padding:8px;">{d['cond']}</td>
                    <td style="padding:8px;">{d['fecha']}</td>
                    <td style="text-align:center; padding:8px;">{btn_html}</td>
                </tr>
                """

            cuerpo_html = f"""
            <html>
            <body style="font-family: Arial, sans-serif;">
                <h2 style="color:#2c3e50;">📊 Actualización de Flota</h2>
                <p>Hola Cintia, se ha realizado el cruce de datos con el ERP. Aquí tienes los vencimientos resultantes:</p>
                <table style="width:100%; border-collapse: collapse; font-size:14px;">
                    <tr style="background-color:#333; color:white;">
                        <th style="padding:8px;">Est</th>
                        <th style="padding:8px;">Matrícula</th>
                        <th style="padding:8px;">Conductor</th>
                        <th style="padding:8px;">Fecha</th>
                        <th style="padding:8px;">Acción</th>
                    </tr>
                    {filas_html}
                </table>
                <p style="font-size:12px; color:#888; margin-top:20px;">Generado automáticamente por tu App de Flota 🚀</p>
            </body>
            </html>
            """

            try:
                msg = MIMEText(cuerpo_html, "html", _charset="utf-8")
                msg["Subject"] = f"🚨 Reporte Vencimientos (Actualizado) - {hoy.strftime('%d/%m/%Y')}"
                msg["From"] = EMAIL_ORIGEN
                msg["To"] = EMAIL_DESTINO

                server = smtplib.SMTP("smtp.gmail.com", 587)
                server.starttls()
                server.login(EMAIL_ORIGEN, EMAIL_PASS)
                server.sendmail(EMAIL_ORIGEN, EMAIL_DESTINO, msg.as_string())
                server.quit()
                
                st.success(f"✅ ¡Correo enviado con éxito a {EMAIL_DESTINO}!")
            
            except Exception as e:
                st.error(f"❌ Error al enviar el correo: {e}")
