"""Pipeline de punta a punta sobre datos sintéticos "sucios", con carga a SQLite."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest
from openpyxl import load_workbook
from sqlalchemy import Engine, create_engine, inspect

from radar_cartera.pipeline import PipelineResult
from radar_cartera.warehouse import VIEWS, ddl, load, read_view

KPI_COLUMNS = [
    "saldo_total", "saldo_vencido", "obligaciones_mora", "par30", "par90", "recaudo",
    "tasa_recuperacion", "gestiones", "contactos", "contactabilidad",
    "promesas_evaluables", "promesas_cumplidas", "efectividad_promesas",
]  # fmt: skip

Run = tuple[PipelineResult, Path, str]


@pytest.fixture
def dw(pipeline_run: Run) -> Iterator[Engine]:
    engine = create_engine(pipeline_run[2])
    yield engine
    engine.dispose()


def test_all_injected_anomalies_are_quarantined(pipeline_run: Run, synthetic) -> None:  # type: ignore[no-untyped-def]
    result, out, _ = pipeline_run
    assert result.quality is not None
    assert result.quality.total_rejected == sum(synthetic.anomalies.values())
    rejected = pd.read_csv(out / "rechazados.csv")
    assert len(rejected) == result.quality.total_rejected
    by_reason = rejected.groupby(["dataset", "motivo"]).size()
    expected = {
        "clientes_duplicados": ("clientes", "cliente_duplicado"),
        "cortes_saldo_negativo": ("cortes", "saldo_negativo"),
        "pagos_valor_negativo": ("pagos", "valor_invalido"),
        "pagos_huerfanos": ("pagos", "obligacion_inexistente"),
        "pagos_duplicados": ("pagos", "pago_duplicado"),
        "gestiones_huerfanas": ("gestiones", "obligacion_inexistente"),
        "gestiones_fecha_futura": ("gestiones", "fecha_gestion_invalida"),
    }
    for anomaly, key in expected.items():
        assert by_reason.get(key, 0) == synthetic.anomalies[anomaly], anomaly


def test_warehouse_tables_and_views_are_created(pipeline_run: Run, dw: Engine) -> None:
    result, _, _ = pipeline_run
    engine = dw
    inspector = inspect(engine)
    assert set(result.rows_loaded) <= set(inspector.get_table_names())
    assert set(VIEWS) <= set(inspector.get_view_names())
    assert result.model is not None
    with engine.connect() as conn:
        count = conn.exec_driver_sql("SELECT COUNT(*) FROM fact_cartera").scalar()
    assert count == len(result.model.fact_cartera)


def test_sql_views_match_pandas_kpis(pipeline_run: Run, dw: Engine) -> None:
    """La misma definición de negocio en SQL (Power BI) y en pandas (reportes) da igual."""
    result, _, _ = pipeline_run
    assert result.kpis is not None
    sql = read_view(dw, "vw_kpi_mensual").sort_values("anio_mes", ignore_index=True)
    py = result.kpis.monthly.sort_values("anio_mes", ignore_index=True)
    assert sql["anio_mes"].tolist() == py["anio_mes"].tolist()
    pd.testing.assert_frame_equal(
        sql[KPI_COLUMNS].astype("float64"),
        py[KPI_COLUMNS].astype("float64"),
        check_exact=False,
        rtol=1e-9,
    )


def test_ranking_view_matches_pandas(pipeline_run: Run, dw: Engine) -> None:
    result, _, _ = pipeline_run
    assert result.kpis is not None
    view = read_view(dw, "vw_ranking_gestores")
    view = view[view["anio_mes"] == result.kpis.month].sort_values(
        ["ranking", "id_gestor"], ignore_index=True
    )
    py = result.kpis.ranking
    assert view["id_gestor"].tolist() == py["id_gestor"].tolist()
    assert view["ranking"].tolist() == py["ranking"].tolist()
    assert view["recaudo_promesas"].astype(float).tolist() == pytest.approx(
        py["recaudo_promesas"].tolist()
    )


def test_roll_rate_view_matches_pandas(pipeline_run: Run, dw: Engine) -> None:
    result, _, _ = pipeline_run
    assert result.kpis is not None
    view = read_view(dw, "vw_roll_rate")
    view = view[view["anio_mes"] == result.kpis.month]
    pivot = view.pivot_table(
        index="bucket_origen", columns="bucket_destino", values="obligaciones", aggfunc="sum"
    )
    counts = result.kpis.roll_counts
    for (origin, dest), n in pivot.stack().dropna().items():
        assert counts.loc[origin, dest] == n
    assert int(view["obligaciones"].sum()) == int(counts.to_numpy().sum())


def test_load_is_idempotent(pipeline_run: Run, dw: Engine) -> None:
    result, _, _ = pipeline_run
    assert result.model is not None
    engine = dw
    first = load(result.model, engine)
    second = load(result.model, engine)
    assert first == second
    with engine.connect() as conn:
        assert (
            conn.exec_driver_sql("SELECT COUNT(*) FROM fact_pagos").scalar() == first["fact_pagos"]
        )


def test_excel_report_structure(pipeline_run: Run) -> None:
    result, out, _ = pipeline_run
    wb = load_workbook(out / result.outputs["excel"])
    assert wb.sheetnames == [
        "Resumen", "Franjas de mora", "Roll rate", "Gestores", "Productos", "Calidad de datos", "Rechazados",
    ]  # fmt: skip
    resumen = wb["Resumen"]
    assert resumen["A8"].value == "Mes"
    assert resumen["F9"].number_format == "0.0%"
    assert len(resumen._charts) == 2
    assert "KpiMensual" in resumen.tables


def test_html_report_embeds_valid_json(pipeline_run: Run) -> None:
    _, out, _ = pipeline_run
    html = (out / "index.html").read_text(encoding="utf-8")
    start = html.index('<script id="payload" type="application/json">') + len(
        '<script id="payload" type="application/json">'
    )
    payload = json.loads(html[start : html.index("</script>", start)])
    assert payload["month"] == payload["monthly"][-1]["anio_mes"]
    assert payload["roll"]["destinations"][-1] == "Salida de cartera"
    assert "chart.js@4.4.1" in html


def test_manifest_traces_the_run(pipeline_run: Run) -> None:
    result, out, _ = pipeline_run
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["run_id"] == result.run_id
    assert (
        manifest["rows_in"]["pagos"]
        == manifest["rows_valid"]["pagos"] + manifest["rows_rejected"]["pagos"]
    )
    assert {"validacion", "modelado", "carga_dw", "kpis"} <= set(manifest["steps_seconds"])


def test_ddl_for_postgres() -> None:
    script = ddl("postgresql")
    assert "CREATE TABLE fact_cartera" in script
    assert "NUMERIC(18, 2)" in script
    assert "PRIMARY KEY (corte_key, obligacion_key)" in script
