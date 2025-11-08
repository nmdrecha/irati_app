
import os, io
import pandas as pd
import streamlit as st
from utils import transform_quiron, prep_two_cols, anti_join_real_minus_quiron

st.set_page_config(page_title="Irati — Comprobación de facturación", layout="wide")

DATA_PATH = "data/TABLA_CODIGOS_DE_FACTURACION.xlsx"

st.sidebar.title("Irati")
st.sidebar.write("Tabla fija de **códigos** para mapeo de conceptos.")

# Estado de la referencia
ref_exists = os.path.exists(DATA_PATH)
if ref_exists:
    st.sidebar.success("Tabla de referencia cargada.")
else:
    st.sidebar.warning("No se encontró tabla de referencia. Súbela en la pestaña **Irati**.")

tab_irati, tab_proceso = st.tabs(["Irati (tabla de códigos)", "Proceso (Quirón vs Real)"])

with tab_irati:
    st.header("Tabla de referencia de códigos")
    st.write("Este archivo se guarda en `data/TABLA_CODIGOS_DE_FACTURACION.xlsx` para uso persistente.")
    uploaded_ref = st.file_uploader("Subir/Actualizar tabla de referencia (Excel con columnas: Conceptos, Códigos)", type=["xlsx"], key="ref")
    if uploaded_ref is not None:
        try:
            df_ref_new = pd.read_excel(uploaded_ref)
            os.makedirs("data", exist_ok=True)
            df_ref_new.to_excel(DATA_PATH, index=False)
            st.success("Referencia actualizada y guardada.")
        except Exception as e:
            st.error(f"Error leyendo/guardando la referencia: {e}")

    if os.path.exists(DATA_PATH):
        df_ref_show = pd.read_excel(DATA_PATH)
        st.caption(f"Filas: {len(df_ref_show)}")
        st.dataframe(df_ref_show, use_container_width=True)

with tab_proceso:
    st.header("1) Transformación de Quirón (Concepto → Código)")
    st.write("Usa la tabla de la pestaña **Irati** como referencia. Lee columnas C (Concepto) y D (NHC).")

    up_q = st.file_uploader("Subir Excel mensual de Quirón", type=["xlsx"], key="quiron")
    up_real = st.file_uploader("Subir Excel de facturación **Real** (2 primeras columnas = historia, código)", type=["xlsx"], key="real")

    btn = st.button("Procesar y generar Excel de errores (Real − Quirón)", type="primary", disabled=not (up_q and up_real and os.path.exists(DATA_PATH)))

    if not os.path.exists(DATA_PATH):
        st.info("Falta la tabla de referencia en la pestaña **Irati**.")
    elif up_q is None or up_real is None:
        st.info("Sube ambos archivos para continuar.")
    else:
        if btn:
            try:
                # cargar referencia
                df_ref = pd.read_excel(DATA_PATH)
                # Quirón original
                df_q = pd.read_excel(up_q, header=0)  # no usamos cabeceras para seleccionar, pero no perdemos la primera fila
                # Transformación paso 1
                df_q_out, no_map = transform_quiron(df_q, df_ref)
                st.subheader("Resultado paso 1: Quirón transformado")
                st.write(f"Filas (tras normalizar/eliminar historias vacías): **{len(df_q_out)}**")
                st.dataframe(df_q_out.head(50), use_container_width=True)

                # Descarga Quirón transformado
                buf_q = io.BytesIO()
                df_q_out.to_excel(buf_q, index=False)
                st.download_button("Descargar Quirón transformado (historia, código)",
                    data=buf_q.getvalue(), file_name="Quiron_transformado.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

                # Reporte no mapeados
                if no_map:
                    st.warning(f"No mapeados ({len(no_map)} conceptos únicos). Muestra 50 primeros:")
                    st.write(no_map[:50])
                else:
                    st.success("Todos los conceptos fueron mapeados a código.")

                # Paso 2: Comparación con Real
                st.header("2) Anti-join: combinaciones en Real y NO en Quirón")
                # Leer Real con header=None
                df_real = pd.read_excel(up_real, header=None)
                df_real_prep = prep_two_cols(df_real)
                # Preparar Quirón (historia, codigo) al mismo formato
                df_q_prep = df_q_out.rename(columns={"numero de historia": "historia"}).copy()
                df_q_prep["codigo"] = df_q_prep["codigo"].astype(str)

                # Eliminar duplicados exactos
                df_q_prep = df_q_prep.drop_duplicates(subset=["historia", "codigo"])

                diff = anti_join_real_minus_quiron(df_real_prep, df_q_prep)

                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Registros únicos en Real", len(df_real_prep))
                with col2:
                    st.metric("Registros únicos en Quirón (transformado)", len(df_q_prep))
                with col3:
                    st.metric("Diferencias (Real − Quirón)", len(diff))

                st.dataframe(diff.head(1000), use_container_width=True)

                # Exportación con dos nombres (con y sin espacios)
                out_name_spaces = st.text_input("Nombre de salida (con espacios)", value="Errores Facturacion.xlsx")
                out_name_nospaces = out_name_spaces.replace(" ", "_")

                if st.button("Generar archivos de salida"):
                    out_buf1 = io.BytesIO(); diff.to_excel(out_buf1, index=False)
                    out_buf2 = io.BytesIO(); diff.to_excel(out_buf2, index=False)
                    st.download_button("Descargar (con espacios)",
                        data=out_buf1.getvalue(), file_name=out_name_spaces,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="dl1")
                    st.download_button("Descargar (sin espacios)",
                        data=out_buf2.getvalue(), file_name=out_name_nospaces,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="dl2")

            except Exception as e:
                st.error(f"Error en el proceso: {e}")
