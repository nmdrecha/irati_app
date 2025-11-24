import re
import unicodedata
import pandas as pd
import numpy as np


def _strip_accents(s: str) -> str:
    if not isinstance(s, str):
        s = "" if s is None else str(s)
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_concept(text: str) -> str:
    """
    Normaliza el 'Concepto' para comparar contra la tabla de referencia:
    - minúsculas
    - sin acentos
    - quitar puntuación básica y espacios múltiples
    - eliminar sufijos tipo '-32-AB25-0005357' al final (heurística)
    """
    if text is None:
        text = ""
    text = str(text)
    t = _strip_accents(text).lower()
    # eliminar espacios invisibles
    t = t.replace("\xa0", " ").replace("\u200b", " ")
    # Heurística: quitar sufijo formado por grupos alfanuméricos separados por guiones al final
    t = re.sub(r"\s*-([A-Za-z0-9]{2,})(-[A-Za-z0-9]{2,})*$", "", t)
    # quitar puntuación común
    t = re.sub(r"[.,;:_/\\]+", " ", t)
    # colapsar espacios
    t = re.sub(r"\s+", " ", t).strip()
    return t


def build_reference_map(df_ref: pd.DataFrame) -> dict:
    """
    df_ref con columnas: Conceptos, Códigos
    Devuelve diccionario de {concepto_normalizado: codigo}
    """
    cols = [c.strip().lower() for c in df_ref.columns]
    if "conceptos" in cols:
        c_con = df_ref.columns[cols.index("conceptos")]
    else:
        c_con = df_ref.columns[0]
    if "codigos" in cols or "códigos" in cols:
        if "codigos" in cols:
            c_cod = df_ref.columns[cols.index("codigos")]
        else:
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
    """
    Mapea un concepto a código:
    1) igual exacto tras normalización
    2) si no hay exacto, buscar el/los conceptos de referencia contenidos en el concepto del parte;
       elegir el más largo (más específico)
    """
    n = normalize_concept(concept)
    if n in ref_map:
        return ref_map[n]

    candidates = [k for k in ref_map.keys() if k and k in n]
    if candidates:
        best = max(candidates, key=len)
        return ref_map[best]
    return ""


def select_concept_and_historia(df: pd.DataFrame) -> pd.DataFrame:
    """
    Selecciona columnas C (índice 2) y D (índice 3) del Excel mensual de Quirón.
    Tolera archivos con más o menos columnas.
    """
    if df.shape[1] < 4:
        cols = [str(c).strip().lower() for c in df.columns]
        idx_con = next((i for i, c in enumerate(cols) if "concepto" in c), 2)
        idx_hist = next(
            (i for i, c in enumerate(cols) if c in ("nhc", "n.h.c", "historia", "nº historia", "numero historia")),
            3,
        )
    else:
        idx_con, idx_hist = 2, 3

    idx_con = min(idx_con, df.shape[1] - 1)
    idx_hist = min(idx_hist, df.shape[1] - 1)

    out = df.iloc[:, [idx_hist, idx_con]].copy()
    out.columns = ["numero de historia", "concepto"]
    return out


def normalize_historia(s):
    """
    Normaliza el número de historia como TEXTO:
    - quita espacios normales, NBSP y zero-width
    - elimina caracteres no numéricos
    - NO convierte a int (no toca ceros ni longitud)
    """
    if pd.isna(s):
        return ""
    s = str(s)
    s = s.replace("\xa0", "").replace("\u200b", "")
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"[^\d]", "", s)  # dejar solo dígitos
    return s


def normalize_codigo(x):
    if pd.isna(x):
        return ""
    s = str(x).replace("\xa0", "").replace("\u200b", "").strip()
    try:
        f = float(s)
        if f.is_integer():
            return str(int(f))
        return s.upper()
    except Exception:
        return s.upper()


def transform_quiron(df_q: pd.DataFrame, df_ref: pd.DataFrame):
    """
    Paso 1: usa la tabla de referencia para convertir Concepto->Código.
    Devuelve df_out (historia, codigo) y lista de conceptos no mapeados.
    """
    ref_map = build_reference_map(df_ref)
    sel = select_concept_and_historia(df_q)
    sel["codigo"] = sel["concepto"].apply(lambda v: map_concept_to_code(v, ref_map))

    sel["numero de historia"] = sel["numero de historia"].apply(normalize_historia)
    sel["codigo"] = sel["codigo"].apply(normalize_codigo)

    # eliminar filas con historia vacía
    sel = sel[sel["numero de historia"] != ""].copy()

    out = sel[["numero de historia", "codigo"]].copy()

    no_map = sel.loc[sel["codigo"] == "", "concepto"].dropna().unique().tolist()
    return out, no_map


def prep_two_cols(df: pd.DataFrame):
    """
    Para el paso 2: usa sólo las dos primeras columnas, header=None.
    Renombra a historia, codigo y normaliza según reglas.
    """
    if df.shape[1] < 2:
        raise ValueError("El archivo debe tener al menos dos columnas.")

    g = df.iloc[:, :2].copy()
    g.columns = ["historia", "codigo"]

    g["historia"] = g["historia"].apply(normalize_historia)
    g["codigo"] = g["codigo"].apply(normalize_codigo)

    g = g[g["historia"] != ""].copy()

    g = g.drop_duplicates(subset=["historia", "codigo"])
    return g


def anti_join_real_minus_quiron(df_real: pd.DataFrame, df_q: pd.DataFrame):
    """
    Devuelve combinaciones (historia, codigo) que están en Real y NO en Quirón.
    Ordena por historia y luego código (texto).
    """
    key = ["historia", "codigo"]
    merged = df_real.merge(df_q, on=key, how="left", indicator=True)
    out = merged[merged["_merge"] == "left_only"][key].copy()
    out = out.sort_values(by=["historia", "codigo"], ascending=[True, True]).reset_index(drop=True)
    return out
