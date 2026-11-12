"""Limpieza y estandarización de datos crudos. Funciones puras y vectorizadas."""

from __future__ import annotations

import unicodedata

import numpy as np
import pandas as pd

from radar_cartera.domain import BUCKET_EDGES, BUCKETS, CIUDADES, RESULTADOS
from radar_cartera.extract import RawData


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


_RESULTADOS_CANON = {_strip_accents(r).casefold(): r for r in RESULTADOS}
_CIUDADES_CANON = {**CIUDADES, **{_strip_accents(v).casefold(): v for v in CIUDADES.values()}}


def normalize_documento(values: pd.Series) -> pd.Series:
    """'1.012.345.678' / ' 1012345678 ' -> '1012345678'."""
    digits = values.astype("string").str.replace(r"\D", "", regex=True)
    return digits.mask(digits == "")


def normalize_name(values: pd.Series) -> pd.Series:
    """Colapsa espacios y aplica mayúscula inicial: '  LAURA   gómez ' -> 'Laura Gómez'."""
    clean = values.astype("string").str.strip().str.replace(r"\s+", " ", regex=True)
    return clean.str.title()


def normalize_catalog(values: pd.Series, catalog: dict[str, str]) -> pd.Series:
    """Mapea variantes (mayúsculas, sin tilde, espacios) al valor canónico; si no existe, NA."""
    keys = (
        values.astype("string")
        .str.strip()
        .map(lambda v: _strip_accents(v).casefold() if isinstance(v, str) else v)
    )
    return keys.map(catalog).astype("string")


def normalize_city(values: pd.Series) -> pd.Series:
    return normalize_catalog(values, _CIUDADES_CANON)


def normalize_resultado(values: pd.Series) -> pd.Series:
    return normalize_catalog(values, _RESULTADOS_CANON)


def parse_money(values: pd.Series) -> pd.Series:
    """Acepta números o texto en formato colombiano: '$ 1.234.567,50' -> 1234567.5."""
    numeric = pd.to_numeric(values, errors="coerce").astype("float64")
    text = values.where(numeric.isna()).astype("string")
    is_negative = text.str.contains("-", regex=False, na=False)
    cleaned = text.str.replace(r"[^\d,]", "", regex=True).str.replace(",", ".", regex=False)
    cleaned = cleaned.mask(cleaned == "")
    parsed = pd.to_numeric(cleaned, errors="coerce").astype("float64")
    parsed = parsed.where(~is_negative.to_numpy(dtype=bool), -parsed)
    return numeric.fillna(parsed)


def parse_dates(values: pd.Series) -> pd.Series:
    """Fechas ISO (o celdas de Excel) y dd/mm/aaaa en la misma columna."""
    text = values.astype("string").str.strip()
    iso = pd.to_datetime(text.str.slice(0, 10), format="%Y-%m-%d", errors="coerce")
    dmy = pd.to_datetime(text, format="%d/%m/%Y", errors="coerce")
    return iso.fillna(dmy)


def parse_datetimes(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values.astype("string").str.strip(), format="ISO8601", errors="coerce")


def aging_bucket(dias_mora: pd.Series) -> pd.Series:
    """Franja de mora como categoría ordenada (0 = 'Al día', 1-30, …, >180)."""
    return pd.cut(dias_mora, bins=BUCKET_EDGES, labels=BUCKETS, ordered=True)


def _int(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values, errors="coerce").astype("Int64")


# ---------------------------------------------------------------------- por dataset
def clean_clientes(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["id_cliente"] = out["id_cliente"].astype("string").str.strip()
    out["documento"] = normalize_documento(out["documento"])
    out["nombre"] = normalize_name(out["nombre"])
    out["ciudad"] = normalize_city(out["ciudad"])
    out["segmento"] = out["segmento"].astype("string").str.strip()
    out["fecha_vinculacion"] = parse_dates(out["fecha_vinculacion"])
    return out


def clean_obligaciones(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ("id_obligacion", "id_cliente", "producto"):
        out[col] = out[col].astype("string").str.strip()
    out["monto_desembolsado"] = parse_money(out["monto_desembolsado"])
    out["plazo_meses"] = _int(out["plazo_meses"])
    out["tasa_mensual"] = pd.to_numeric(out["tasa_mensual"], errors="coerce")
    out["fecha_desembolso"] = parse_dates(out["fecha_desembolso"])
    return out


def clean_gestores(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["id_gestor"] = out["id_gestor"].astype("string").str.strip()
    out["nombre"] = normalize_name(out["nombre"])
    out["equipo"] = out["equipo"].astype("string").str.strip()
    return out


def clean_cortes(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["id_obligacion"] = out["id_obligacion"].astype("string").str.strip()
    out["fecha_corte"] = parse_dates(out["fecha_corte"])
    out["saldo_capital"] = parse_money(out["saldo_capital"])
    out["dias_mora"] = _int(out["dias_mora"])
    return out


def clean_pagos(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["id_pago"] = out["id_pago"].astype("string").str.strip()
    out["id_obligacion"] = out["id_obligacion"].astype("string").str.strip()
    out["fecha_pago"] = parse_dates(out["fecha_pago"])
    out["valor"] = parse_money(out["valor"])
    out["canal"] = out["canal"].astype("string").str.strip()
    return out


def clean_gestiones(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in ("id_gestion", "id_obligacion", "id_gestor", "canal"):
        out[col] = out[col].astype("string").str.strip()
    out["resultado_original"] = out["resultado"]
    out["resultado"] = normalize_resultado(out["resultado"])
    out["fecha_gestion"] = parse_datetimes(out["fecha_gestion"])
    out["fecha_promesa"] = parse_dates(out["fecha_promesa"])
    out["valor_promesa"] = parse_money(out["valor_promesa"])
    return out


def clean_all(raw: RawData) -> RawData:
    return RawData(
        clientes=clean_clientes(raw.clientes),
        obligaciones=clean_obligaciones(raw.obligaciones),
        gestores=clean_gestores(raw.gestores),
        cortes=clean_cortes(raw.cortes),
        pagos=clean_pagos(raw.pagos),
        gestiones=clean_gestiones(raw.gestiones),
    )


def month_label(dates: pd.Series) -> pd.Series:
    """'2026-10' para agrupar por mes calendario."""
    return dates.dt.strftime("%Y-%m")


def safe_ratio(num: pd.Series, den: pd.Series) -> pd.Series:
    return (num / den.replace(0, np.nan)).astype("float64")
