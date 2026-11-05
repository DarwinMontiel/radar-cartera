"""Carga real a PostgreSQL y verificación cruzada de las vistas contra pandas.

Requiere ``CARTERA_DATABASE_URL`` (en CI: service container de PostgreSQL 16).
"""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, inspect

from cartera_analytics.pipeline import run_pipeline
from cartera_analytics.warehouse import VIEWS, read_view

pytestmark = pytest.mark.integration


@pytest.fixture
def pg_url() -> str:
    url = os.getenv("CARTERA_DATABASE_URL")
    if not url:
        pytest.skip("CARTERA_DATABASE_URL no definida")
    return url


def test_pipeline_against_postgres(raw_dir: Path, tmp_path: Path, pg_url: str) -> None:
    result = run_pipeline(raw_dir, tmp_path, database_url=pg_url)
    engine = create_engine(pg_url)
    assert set(VIEWS) <= set(inspect(engine).get_view_names())

    assert result.kpis is not None
    sql = read_view(engine, "vw_kpi_mensual").sort_values("anio_mes", ignore_index=True)
    py = result.kpis.monthly.sort_values("anio_mes", ignore_index=True)
    cols = [
        "saldo_total",
        "saldo_vencido",
        "par30",
        "recaudo",
        "tasa_recuperacion",
        "contactabilidad",
    ]
    pd.testing.assert_frame_equal(
        sql[cols].apply(pd.to_numeric).astype("float64"), py[cols].astype("float64"), rtol=1e-9
    )

    # Segunda corrida: la carga es idempotente (mismas filas, sin duplicados ni errores de PK).
    again = run_pipeline(raw_dir, tmp_path, database_url=pg_url)
    assert again.rows_loaded == result.rows_loaded


def test_analytical_queries_run_on_postgres(raw_dir: Path, tmp_path: Path, pg_url: str) -> None:
    """Las consultas de ejemplo de sql/consultas_analiticas.sql deben ser SQL válido."""
    run_pipeline(raw_dir, tmp_path, database_url=pg_url)
    script = (Path(__file__).parents[2] / "sql" / "consultas_analiticas.sql").read_text("utf-8")
    statements = [s.strip() for s in script.split(";") if "SELECT" in s.upper()]
    assert len(statements) == 5
    engine = create_engine(pg_url)
    with engine.connect() as conn:
        for statement in statements:
            rows = conn.exec_driver_sql(statement).fetchall()
            assert rows is not None
