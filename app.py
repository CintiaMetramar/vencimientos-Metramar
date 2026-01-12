import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import urllib.parse
import io
from fpdf import FPDF

# ==========================================
# 🚛 CONFIGURACIÓN Y ESTÁNDARES
# ==========================================
st.set_page_config(page_title="Gestión Flota - Metramar", page_icon="🚛", layout="wide")

# Añadimos 'Fecha_Aviso' al maestro para recordar notificaciones
COLS_SEMANAL = ['Tipo Dococumento', 'Empresa', 'Conductor', 'Vehiculo', 'Matricula', 'Marca', 'TipoVehiculo', 'Vencimiento']
COLS_MAESTRO = ['Tipo', 'Empresa', 'Conductor', 'Vehículo', 'Matricula', 'Marca', 'Tipo de vehículo', 'Fecha de vencimiento', 'Telefono', 'Fecha_Aviso']
MAPEO_A_MAESTRO = {'Tipo Dococumento': 'Tipo', 'Vehiculo': 'Vehículo', 'TipoVehiculo': 'Tipo de vehículo', 'Vencimiento': 'Fecha de vencimiento'}

# ==========================================
# 🔐 1. SEGURIDAD
# ==========================================
def check_password():
    if "password_correct" not in st.session_state:
        # Pide la contraseña si no está en sesión (asegúrate de tener .streamlit/secrets.toml configurado)
        # Para pruebas locales puedes comentar las lineas de secrets y poner: return True
        try:
            st.text_input("🔑 Contraseña:", type="password", on_change=lambda: st.session_state.update({"password_correct": st.session_state["password"] == st.secrets["password"]}), key="password")
            return False
        except:
            return True # Modo prueba si no hay secrets
    return st.session_state["password_correct"]

if not check_password():
    st.stop()

# ==========================================
# 🛠️ FUNCIONES AUXILIARES (PDF MEJORADO)
# ==========================================
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 15)
        self.cell(0, 10, 'Reporte de Vencimientos - Metramar', 0, 1, 'C')
        self.ln(5)

def generar_pdf(dataframe):
    pdf = PDF()
    pdf.add_page()
    pdf.set_font("Arial", size=9) # Letra un poco más pequeña para que quepa el Tipo
    pdf.set_fill_color(200, 220, 255)
    
    # NUEVAS COLUMNAS PDF: Ajuste de anchos para incluir "Tipo"
    # Total ancho A4 ~190 útil. 
    # Estado(20) + Tipo(30) + Matricula(30) + Conductor(70) + Vencimiento(30) = 180 (OK)
    cols = [("Estado", 20), ("Tipo", 30), ("Matricula", 30), ("Conductor", 70), ("Vencimiento", 30)]
    
    for txt, w in cols: pdf.cell(w, 10, txt, 1, 0, 'C', 1)
    pdf.ln()
    
    for _, row in dataframe.iterrows():
        estado = "VENCIDO" if "🔴" in row['bola'] else ("PROXIMO" if "🟡" in row['bola'] else "OK")
        
        # Limpieza de textos para evitar errores de caracteres latinos en FPDF básico
        tipo_clean = str(row.get('Tipo', 'Doc'))[:15].encode('latin-1', 'replace').decode('latin-1')
        cond_clean = str(row['Conductor'])[:30].encode('latin-1', 'replace').decode('latin-1')
        
        pdf.cell(20, 10, estado, 1)
        pdf.cell(30, 10, tipo_clean, 1) # Nueva columna
        pdf.cell(30, 10, str(row['Matricula']), 1)
        pdf.cell(70, 10, cond_clean, 1)
        pdf.cell(30, 10, str(row['Fecha_Str']), 1)
        pdf.ln()
        
    return pdf.output(dest='S').encode('latin-1', 'replace')

# ==========================================
# 📂 2. CARGA Y PROCESAMIENTO
# ==========================================
st.title("🚛 Centro de Control: Metramar")

col1, col2 = st.columns(2)
with col1:
    uploaded_master = st.file_uploader("1️⃣ Fichero MAESTRO (Debe tener columna 'Fecha_Aviso')", type=["xlsx"])
with col2:
    uploaded_weekly = st.file_uploader("2️⃣ Fichero SEMANAL ERP", type=["xls", "xlsx"])

if uploaded_master and uploaded_weekly:
    df_final = pd.DataFrame()
    
    try:
        # Carga
        df_m = pd.read_excel(uploaded_master)
        
        # --- MEJORA PERSISTENCIA ---
        # Si es la primera vez que usas el script nuevo, quizás no exista la columna 'Fecha_Aviso'
        if 'Fecha_Aviso' not in df_m.columns:
            df_m['Fecha_Aviso'] = pd.NaT # Crear vacía si no existe
            st.toast("ℹ️ Columna de notificaciones creada automáticamente.")

        # Carga semanal (Soporte xls antiguo)
        if uploaded_weekly.name.endswith('.xls'):
            df_s = pd.read_excel(uploaded_weekly, engine='xlrd')
        else:
            df_s = pd.read_excel(uploaded_weekly)

        # Validación básica (ignora columnas extra del maestro si las hubiera)
        missing_s = [c for c in COLS_SEMANAL if c not in df_s.columns]
        # Validamos del maestro solo las esenciales, ignorando Fecha_Aviso para no bloquear
        essential_m = [c for c in COLS_MAESTRO if c != 'Fecha_Aviso'] 
        missing_m = [c for c in essential_m if c not in df_m.columns]

        if missing_s or missing_m:
            st.error(f"❌ Error de columnas.\nFaltan en Semanal: {missing_s}\nFaltan en Maestro: {missing_m}")
            st.stop()

        # Fusión
        df_s_clean = df_s[COLS_SEMANAL].rename(columns=MAPEO_A_MAESTRO)
        
        # Normalizar claves de cruce
        df_m['Matricula_Match'] = df_m['Matricula'].astype(str).str.strip().str.upper()
        df_s_clean['Matricula_Match'] = df_s_clean['Matricula'].astype(str).str.strip().str.upper()

        # Merge inteligente
        # Nos traemos Fecha vencimiento Y el Tipo del semanal (que es el dato fresco)
        merged = pd.merge(df_m, df_s_clean[['Matricula_Match', 'Fecha de vencimiento', 'Tipo']], 
                          on='Matricula_Match', how='left', suffixes=('_old', '_new'))
        
        # Actualización de datos: Priorizamos lo nuevo del semanal
        merged['Fecha de vencimiento'] = merged['Fecha de vencimiento_new'].fillna(merged['Fecha de vencimiento_old'])
        merged['Tipo'] = merged['Tipo_new'].fillna(merged['Tipo_old']) # Actualizar tipo si cambió
        
        # Limpieza
        df_final = merged.drop(columns=['Matricula_Match', 'Fecha de vencimiento_new', 'Fecha de vencimiento_old', 'Tipo_new', 'Tipo_old'], errors='ignore')
        df_final['Fecha de vencimiento'] = pd.to_datetime(df_final['Fecha de vencimiento'], errors='coerce')
        df_final['Fecha_Aviso'] = pd.to_datetime(df_final['Fecha_Aviso'], errors='coerce')

    except Exception as e:
        st.error(f"⚠️ Error en el procesado: {e}")
        st.stop()

    # ==========================================
    # 🚦 3. INFORME Y ALERTAS
    # ==========================================
    st.divider()
    st.subheader("📊 Análisis de Vencimientos Próximos")
    
    hoy = datetime.now()
    rango_alerta = hoy + timedelta(days=30)
    limite_pasado = hoy - timedelta(days=15)

    # Filtrado
    mask = (df_final['Fecha de vencimiento'] >= limite_pasado) & \
           (df_final['Fecha de vencimiento'] <= rango_alerta)
    
    df_alertas = df_final[mask].copy()

    if df_alertas.empty:
        st.success("✅ Todo al día. No se requieren acciones.")
    else:
        resumen_pdf = [] # Lista separada para el PDF (sin botones)
        
        # Iteramos sobre las alertas
        # Usamos st.data_editor o checkboxes individuales? Checkboxes es más claro aquí.
        
        st.info("💡 INSTRUCCIÓN: Envía el WhatsApp y luego marca la casilla 'Ya avisado'. Al final descarga el Maestro Actualizado.")
        
        encabezados = st.columns([0.5, 1, 1, 2, 1, 1.5, 1])
        encabezados[0].markdown("**Estado**")
        encabezados[1].markdown("**Tipo**") # Nueva columna visual
        encabezados[2].markdown("**Matrícula**")
        encabezados[3].markdown("**Conductor**")
        encabezados[4].markdown("**Vencimiento**")
        encabezados[5].markdown("**Acción WhatsApp**")
        encabezados[6].markdown("**¿Notificado?**") # Checkbox
        st.divider()

        indices_avisados = []

        for index, row in df_alertas.iterrows():
            fecha_venc = row['Fecha de vencimiento']
            fecha_aviso = row['Fecha_Aviso']
            conductor = row.get('Conductor', 'Sin Asignar')
            matricula = row.get('Matricula', 'S/M')
            tipo_doc = row.get('Tipo', 'Doc')

            # Lógica de Semáforo
            if pd.isna(fecha_venc): bola = "⚪"
            elif fecha_venc < hoy: bola = "🔴"
            elif fecha_venc <= hoy + timedelta(days=7): bola = "🟡"
            else: bola = "🟢"

            # Lógica de "Ya Avisado"
            # Si se avisó hace menos de 7 días, lo consideramos "Gestionado"
            ya_gestionado = False
            estado_aviso = "Pendiente"
            if pd.notna(fecha_aviso):
                dias_desde_aviso = (hoy - fecha_aviso).days
                if dias_desde_aviso < 7:
                    ya_gestionado = True
                    estado_aviso = f"✅ Avisado hace {dias_desde_aviso} días"
                    bola = "✅" # Cambiamos semáforo si ya está controlado

            fecha_str = fecha_venc.strftime('%d/%m') if pd.notna(fecha_venc) else "S/D"
            
            # --- GENERACIÓN LINK WHATSAPP (Igual que antes) ---
            texto = (f"🚨 *AVISO {tipo_doc}* 🚨\n"
                     f"Hola {conductor}, el vehículo {matricula} tiene caducidad próxima.\n"
                     f"Documento: {tipo_doc}\nFecha: {fecha_str}\n"
                     "Por favor contacta con oficina.")
            
            wa_link = None
            tel = str(row.get('Telefono', '')).replace(".0", "").strip()
            if tel and tel != "nan":
                tel_clean = "".join(filter(str.isdigit, tel))
                if len(tel_clean) == 9: tel_clean = "34" + tel_clean
                wa_link = f"https://wa.me/{tel_clean}?text={urllib.parse.quote(texto)}"

            # --- RENDERIZADO EN PANTALLA ---
            c1, c2, c3, c4, c5, c6, c7 = st.columns([0.5, 1, 1, 2, 1, 1.5, 1])
            
            c1.write(bola)
            c2.write(tipo_doc) # Visualizar Tipo
            c3.write(matricula)
            c4.write(conductor)
            c5.write(fecha_str)
            
            # Botón Whatsapp
            if wa_link: 
                c6.link_button(f"📲 WhatsApp", wa_link, disabled=ya_gestionado)
            else: 
                c6.caption("🚫 Sin tel.")

            # Checkbox de persistencia
            # Usamos el index como key única. Si ya estaba gestionado, lo marcamos por defecto.
            marcado = c7.checkbox("Marcar", value=ya_gestionado, key=f"chk_{index}")
            
            if marcado:
                indices_avisados.append(index)

            st.divider()
            
            # Guardamos para PDF (incluyendo el Tipo)
            resumen_pdf.append({
                "bola": bola, 
                "Tipo": tipo_doc, 
                "Matricula": matricula, 
                "Conductor": conductor, 
                "Fecha_Str": fecha_str
            })

        # --- ACTUALIZACIÓN DEL MAESTRO ---
        # Si se marcó el checkbox, actualizamos la fecha de aviso a HOY en el dataframe principal
        if indices_avisados:
            df_final.loc[indices_avisados, 'Fecha_Aviso'] = hoy

        # ==========================================
        # 📥 4. DESCARGAS
        # ==========================================
        st.subheader("📥 Exportar Resultados y Guardar Cambios")
        
        col_a, col_b = st.columns(2)
        with col_a:
            # PDF con la nueva columna Tipo
            if resumen_pdf:
                pdf_bytes = generar_pdf(pd.DataFrame(resumen_pdf))
                st.download_button("📄 Descargar PDF (Con Tipo)", pdf_bytes, f"Vencimientos_{datetime.now().strftime('%d-%m')}.pdf", "application/pdf")
        
        with col_b:
            # EXCEL MAESTRO ACTUALIZADO (CRÍTICO PARA LA PERSISTENCIA)
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df_final.to_excel(writer, index=False)
            
            st.download_button(
                "💾 Descargar MAESTRO ACTUALIZADO (Importante)", 
                output.getvalue(), 
                f"Maestro_Flota_{datetime.now().strftime('%Y%m%d')}.xlsx",
                help="Descarga este archivo y úsalo como Maestro la semana que viene para recordar a quién has avisado."
            )
