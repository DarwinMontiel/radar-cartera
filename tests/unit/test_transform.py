from __future__ import annotations

import pandas as pd
import pytest

from radar_cartera.transform import (
    aging_bucket,
    normalize_city,
    normalize_documento,
    normalize_name,
    normalize_resultado,
    parse_dates,
    parse_money,
)


def test_normalize_documento_removes_separators() -> None:
    out = normalize_documento(pd.Series(["1.012.345.678", " 1012345678 ", "CC 52.123.456", ""]))
    assert out.tolist()[:3] == ["1012345678", "1012345678", "52123456"]
    assert pd.isna(out.iloc[3])


def test_normalize_name_collapses_spaces_and_case() -> None:
    out = normalize_name(pd.Series(["  LAURA   gómez RÍOS ", "andrés pérez"]))
    assert out.tolist() == ["Laura Gómez Ríos", "Andrés Pérez"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("bogota", "Bogotá"),
        ("  MEDELLIN ", "Medellín"),
        ("Cali", "Cali"),
        ("Bogota D.C.", "Bogotá"),
    ],
)
def test_normalize_city(raw: str, expected: str) -> None:
    assert normalize_city(pd.Series([raw])).iloc[0] == expected


def test_unknown_city_becomes_na() -> None:
    assert pd.isna(normalize_city(pd.Series(["Atlantis"])).iloc[0])


def test_normalize_resultado_is_accent_and_case_insensitive() -> None:
    out = normalize_resultado(
        pd.Series([" promesa de pago ", "BUZÓN DE VOZ", "buzon de voz", "otro"])
    )
    assert out.tolist()[:3] == ["Promesa de pago", "Buzón de voz", "Buzón de voz"]
    assert pd.isna(out.iloc[3])


def test_parse_money_handles_numbers_and_colombian_format() -> None:
    raw = pd.Series(
        [2500, 1234.5, "$ 1.234.567", "1.234.567,50", "-$ 80.000", "n/a", None], dtype=object
    )
    out = parse_money(raw)
    assert out.tolist()[:5] == [2500.0, 1234.5, 1234567.0, 1234567.5, -80000.0]
    assert out.iloc[5:].isna().all()


def test_parse_dates_mixed_formats() -> None:
    raw = pd.Series(
        ["2026-10-03", "03/10/2026", pd.Timestamp("2026-10-03"), "31/02/2026", None], dtype=object
    )
    out = parse_dates(raw)
    assert (out.iloc[:3] == pd.Timestamp("2026-10-03")).all()
    assert out.iloc[3:].isna().all()


@pytest.mark.parametrize(
    ("dias", "bucket"),
    [(0, "Al día"), (1, "1-30"), (30, "1-30"), (31, "31-60"), (60, "31-60"), (61, "61-90"),
     (90, "61-90"), (91, "91-180"), (180, "91-180"), (181, ">180"), (999, ">180")],
)  # fmt: skip
def test_aging_bucket_boundaries(dias: int, bucket: str) -> None:
    assert aging_bucket(pd.Series([dias])).iloc[0] == bucket
