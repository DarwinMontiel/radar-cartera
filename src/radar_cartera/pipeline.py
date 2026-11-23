"""Orquestación del ETL: extraer → limpiar → validar → modelar → cargar → KPIs → reportes."""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, TypeVar

import pandas as pd
from sqlalchemy import create_engine

from radar_cartera import __version__
from radar_cartera.extract import RawData, read_raw
from radar_cartera.kpis import KpiBundle, compute_all
from radar_cartera.model import StarSchema, build_model
from radar_cartera.quality import QualityReport, validate_all
from radar_cartera.report_excel import write_excel
from radar_cartera.report_html import write_html
from radar_cartera.transform import clean_all, scope_to_cut
from radar_cartera.warehouse import load

log = logging.getLogger("radar_cartera")
T = TypeVar("T")


@dataclass
class PipelineResult:
    run_id: str
    as_of: date
    started_at: datetime
    finished_at: datetime | None = None
    steps: dict[str, float] = field(default_factory=dict)
    rows_in: dict[str, int] = field(default_factory=dict)
    rows_valid: dict[str, int] = field(default_factory=dict)
    rows_out_of_scope: dict[str, int] = field(default_factory=dict)
    rows_loaded: dict[str, int] = field(default_factory=dict)
    outputs: dict[str, str] = field(default_factory=dict)
    quality: QualityReport | None = None
    model: StarSchema | None = None
    kpis: KpiBundle | None = None

    def manifest(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "version": __version__,
            "as_of": self.as_of.isoformat(),
            "started_at": self.started_at.isoformat(timespec="seconds"),
            "finished_at": self.finished_at.isoformat(timespec="seconds")
            if self.finished_at
            else None,
            "steps_seconds": self.steps,
            "rows_in": self.rows_in,
            "rows_valid": self.rows_valid,
            "rows_rejected": self.quality.rejected_by_dataset() if self.quality else {},
            "rows_out_of_scope": self.rows_out_of_scope,
            "rows_loaded": self.rows_loaded,
            "outputs": self.outputs,
        }


@contextmanager
def _step(result: PipelineResult, name: str) -> Iterator[None]:
    start = time.perf_counter()
    log.info("paso=%s estado=inicio run=%s", name, result.run_id)
    yield
    result.steps[name] = round(time.perf_counter() - start, 3)
    log.info("paso=%s estado=fin segundos=%.3f", name, result.steps[name])


def _timed(result: PipelineResult, name: str, fn: Callable[[], T]) -> T:
    with _step(result, name):
        return fn()


def run_pipeline(
    raw_dir: Path,
    output_dir: Path,
    as_of: date | None = None,
    database_url: str | None = None,
) -> PipelineResult:
    started = datetime.now(UTC)
    run_id = f"{started:%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"

    t0 = time.perf_counter()
    raw: RawData = read_raw(raw_dir)
    cleaned = clean_all(raw)
    cut = as_of or cleaned.cortes["fecha_corte"].max().date()
    # Reproceso de un mes pasado: lo posterior al corte pedido queda fuera de alcance, no en
    # cuarentena (ver transform.scope_to_cut).
    scoped, out_of_scope = scope_to_cut(cleaned, cut)
    result = PipelineResult(run_id=run_id, as_of=cut, started_at=started)
    result.rows_in = raw.row_counts()
    result.rows_out_of_scope = out_of_scope
    result.steps["extraccion_y_limpieza"] = round(time.perf_counter() - t0, 3)
    log.info("paso=extraccion_y_limpieza estado=fin run=%s filas=%s", run_id, result.rows_in)
    if out_of_scope:
        log.info("alcance corte=%s fuera_de_alcance=%s", cut.isoformat(), out_of_scope)

    validated, quality = _timed(result, "validacion", lambda: validate_all(scoped, cut))
    result.quality = quality
    result.rows_valid = validated.row_counts()
    last_cut = validated.cortes["fecha_corte"].max()
    if pd.isna(last_cut):
        raise ValueError(f"No hay cortes de cartera válidos hasta el {cut:%Y-%m-%d}.")
    month = f"{last_cut:%Y-%m}"

    model = _timed(result, "modelado", lambda: build_model(validated, cut))
    result.model = model

    # Antes de la carga: la URL del DW puede apuntar dentro de la carpeta de salida
    # (p. ej. sqlite:///reports/dw.sqlite en el inicio rápido), que aún no existe.
    output_dir.mkdir(parents=True, exist_ok=True)
    if database_url:
        engine = create_engine(database_url, future=True)
        try:
            result.rows_loaded = _timed(result, "carga_dw", lambda: load(model, engine))
        finally:
            engine.dispose()

    kpis = _timed(result, "kpis", lambda: compute_all(model, month))
    result.kpis = kpis

    generated = datetime.now()
    excel = output_dir / f"reporte_cartera_{kpis.month}.xlsx"
    _timed(result, "reporte_excel", lambda: write_excel(kpis, quality, excel, run_id, generated))
    html = output_dir / "index.html"
    _timed(
        result,
        "reporte_html",
        lambda: write_html(kpis, quality, html, run_id, generated, excel_name=excel.name),
    )
    rejected = output_dir / "rechazados.csv"
    quality.rejected_frame().to_csv(rejected, index=False, encoding="utf-8")
    kpis.monthly.to_csv(output_dir / "kpi_mensual.csv", index=False, encoding="utf-8")

    result.outputs = {
        "excel": excel.name,
        "html": html.name,
        "rechazados": rejected.name,
        "kpi_mensual": "kpi_mensual.csv",
    }
    result.finished_at = datetime.now(UTC)
    (output_dir / "manifest.json").write_text(
        json.dumps(result.manifest(), indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log.info("pipeline=ok run=%s rechazados=%d", run_id, quality.total_rejected)
    return result
