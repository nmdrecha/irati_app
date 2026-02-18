import re
import unicodedata
import pandas as pd
import numpy as np

#############################################
# Normalización de textos y conceptos
#############################################

def _strip_accents(s: str) -> str:
    if not isinstance(s, str):
        s = "" if s is None else str(s)
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_concept(text: str) -> str:
    """Normaliza el concepto para comparación."""
    if text is None:
        text = ""
    text = str(text)

    t = _strip_accents(text).lower()

    # eliminar espacios invisibles
    t = t.replace("\xa0", " ").replace("\u200b", " ")

    # eliminar sufijos tipo -32-AB25-0005357
    t = re.sub(r"\s*-([A-Za-z0-9]{2,})(-[A-Za-z0-9]{2,})*$", "", t)

    # quitar puntuación
    t = re.sub(r"[.,;:_/\\]+", " ", t)

    # colapsar espacios
    t = re.sub(r"\s+", " ", t).strip()

    return t


def build_reference_map(df_ref: pd.DataFrame) -> dict:
    """Construye diccionario concepto_normalizado → código."""
    cols = [c.strip().lower() for c in df_ref.columns]

    # detectar columnas automáticamente
    if "conceptos" in cols:
        c_con = df_ref.columns[cols.index("conceptos")]
    else:
        c_con = df_ref.columns[0]

    if "codigos" in cols:
        c_cod = df_ref.columns[cols.index("codigos")]
    elif "códigos" in cols:
        c_cod = df_ref.columns[cols.index("códigos")]
    else:
        c_cod = df_ref.columns[1]

    ref_map = {}
    for _, row in df_ref[[c_con, c_cod]].dropna(how="all").iterrows():
        concept = normalize_concept(row[c_con])
        code = str(row[c_cod]).strip() if pd.notna(row[c_cod]) else ""
        if concept:
            ref_map[concept] = code

    return ref_map


def map_concept_to_code(concept: str, ref_map: dict) -> str:
    """Mapeo exacto o por 'contains' del concepto."""
    n = normalize_concept(concept)
    if n in ref_map:
        return ref_map[n]

    # búsqueda del concepto más largo contenido en el texto
    candidates = [k for k in ref_map.keys() if k and k in n]
    if candidates:
        return ref_map[max(candidates, key=len)]

    return ""


def select_concept_and_historia(df: pd.DataFrame) -> pd.DataFrame:
    """
    Selecciona columnas usando encabezados:
    - 'NHC' → numero de historia
    - 'Concepto' → concepto
    (sin depender de posiciones)
    """

    # normalizar encabezados
    cols = [str(c).strip().lower() for c in df.columns]

    try:
        idx_hist = next(i for i, c in enumerate(cols) if "nhc" in c)
    except StopIteration:
        raise ValueError("No se encuentra columna NHC en el Excel de Quirón")

    try:
        idx_con = next(i for i, c in enumerate(cols) if "concepto" in c)
    except StopIteration:
        raise ValueError("No se encuentra columna Concepto en el Excel de Quirón")

    out = df.iloc[:, [idx_hist, idx_con]].copy()
    out.columns = ["numero de historia", "concepto"]

    return out

#############################################
# NORMALIZACIÓN FIABLE DEL NÚMERO DE HISTORIA
#############################################

def normalize_historia(s):
    """
    Normaliza el número de historia como TEXTO, sin añadir ceros.
    Maneja correctamente casos como:
    - 6078.0 → "6078"
    - "6078.0" → "6078"
    - "  6078 " → "6078"
    - cualquier cosa no numérica → dígitos limpios.
    """
    # caso nulo
    if pd.isna(s):
        return ""

    # caso número (float o int)
    if isinstance(s, (int, float, np.number)):
        try:
            return str(int(round(s)))  # 6078.0 → 6078
        except Exception:
            pass

    # caso texto
    s = str(s).strip().replace("\xa0", "").replace("\u200b", "")

    # texto que representa float: "6078.0" / "6078,0" → 6078
    if re.fullmatch(r"\d+([.,]\d+)?", s):
        s = re.split(r"[.,]", s)[0]
        return s

    # limpieza genérica
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[^\d]", "", s)

    return s


#############################################
# Normalización código
#############################################

def normalize_codigo(x):
    if pd.isna(x):
        return ""
    s = str(x).replace("\xa0", "").replace("\u200b", "").strip()

    # si es float de excel: "712.0" → "712"
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
        return s.upper()
    except Exception:
        return s.upper()


#############################################
# TRANSFORMACIÓN QUIRÓN
#############################################

def transform_quiron(df_q: pd.DataFrame, df_ref: pd.DataFrame):
    """Paso 1: Quirón → (historia, código) usando tabla de referencia."""
    ref_map = build_reference_map(df_ref)
    sel = select_concept_and_historia(df_q)

    sel["codigo"] = sel["concepto"].apply(lambda v: map_concept_to_code(v, ref_map))
    sel["numero de historia"] = sel["numero de historia"].apply(normalize_historia)
    sel["codigo"] = sel["codigo"].apply(normalize_codigo)

    # eliminar filas sin historia
    sel = sel[sel["numero de historia"] != ""].copy()

    out = sel[["numero de historia", "codigo"]].copy()

    no_map = (
        sel.loc[sel["codigo"] == "", "concepto"]
        .dropna()
        .unique()
        .tolist()
    )
    return out, no_map


#############################################
# PREPARACIÓN DE TABLA REAL
#############################################

def prep_two_cols(df: pd.DataFrame):
    """Paso 2: normaliza archivo Real."""
    if df.shape[1] < 2:
        raise ValueError("El archivo debe tener al menos dos columnas.")

    g = df.iloc[:, :2].copy()
    g.columns = ["historia", "codigo"]

    g["historia"] = g["historia"].apply(normalize_historia)
    g["codigo"] = g["codigo"].apply(normalize_codigo)

    g = g[g["historia"] != ""].copy()

    g = g.drop_duplicates(subset=["historia", "codigo"])

    return g


#############################################
# ANTI-JOIN (REAL – QUIRÓN)
#############################################

def anti_join_real_minus_quiron(df_real: pd.DataFrame, df_q: pd.DataFrame):
    """Devuelve combinaciones en Real que NO están en Quirón."""
    key = ["historia", "codigo"]
    merged = df_real.merge(df_q, on=key, how="left", indicator=True)
    out = merged[merged["_merge"] == "left_only"][key].copy()
    out = out.sort_values(by=["historia", "codigo"], ascending=[True, True])
    out = out.reset_index(drop=True)
    return out
