"""Tablero HTML autocontenido (Chart.js) publicado en GitHub Pages por el pipeline de CI."""

from __future__ import annotations

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from jinja2 import Environment, PackageLoader, select_autoescape
from markupsafe import Markup

from cartera_analytics import __version__
from cartera_analytics.kpis import KpiBundle
from cartera_analytics.quality import QualityReport


def _clean(value: Any) -> Any:
    """Convierte tipos de numpy/pandas a JSON nativo (NaN -> null)."""
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_clean(v) for v in value]
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None  # NaN / ±inf no son JSON válido
    if value is pd.NA or value is pd.NaT:
        return None
    return value


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    return [_clean(r) for r in df.to_dict(orient="records")]


def build_payload(kpis: KpiBundle, quality: QualityReport, run: dict[str, Any]) -> dict[str, Any]:
    latest = _clean(kpis.latest.to_dict())
    return {
        "run": run,
        "month": kpis.month,
        "latest": latest,
        "monthly": _records(kpis.monthly),
        "buckets": _records(kpis.buckets),
        "roll": {
            "origins": list(kpis.roll_rates.index),
            "destinations": list(kpis.roll_rates.columns),
            "rates": _clean(kpis.roll_rates.to_numpy().tolist()),
            "counts": _clean(kpis.roll_counts.to_numpy().tolist()),
        },
        "ranking": _records(kpis.ranking),
        "products": _records(kpis.by_product),
        "channels": _records(kpis.by_channel),
        "quality": _records(quality.to_frame()),
        "rejected": _clean(quality.rejected_by_dataset()),
    }


def write_html(
    kpis: KpiBundle,
    quality: QualityReport,
    path: Path,
    run_id: str,
    generated: datetime,
    excel_name: str | None = None,
) -> Path:
    env = Environment(
        loader=PackageLoader("cartera_analytics", "templates"),
        autoescape=select_autoescape(["html", "j2"]),
    )
    run = {
        "id": run_id,
        "generated": generated.isoformat(timespec="seconds"),
        "version": __version__,
        "excel": excel_name,
    }
    payload = build_payload(kpis, quality, run)
    # JSON embebido en <script type="application/json">: se neutraliza "</" para evitar inyección.
    data = Markup(json.dumps(payload, ensure_ascii=False).replace("</", "<\\/"))  # noqa: S704
    html = env.get_template("reporte.html.j2").render(data=data, run=run, month=kpis.month)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")
    return path
