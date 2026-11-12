from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from radar_cartera.extract import RawData
from radar_cartera.model import StarSchema, build_model
from radar_cartera.pipeline import PipelineResult, run_pipeline
from radar_cartera.synthetic import (
    SyntheticConfig,
    SyntheticData,
    dirty_exports,
    generate,
    write_raw,
)

AS_OF = date(2026, 10, 31)


def ts(value: str | None) -> pd.Timestamp:
    return pd.Timestamp(value) if value else pd.NaT


def tiny_data() -> RawData:
    """Escenario calculado a mano (ver docstrings de tests/unit/test_kpis.py).

    Corte sep: OB1 al día (1.000), OB2 45 días (2.000), OB3 100 días (3.000).
    Corte oct: OB1 10 días (1.000), OB2 al día (1.500), OB3 salió de cartera.
    Pagos: OB3 100 el 10-sep; OB2 600 el 15-oct.
    Gestiones oct: G01 promete OB2 (600 al 14-oct, cumplida), G01 no contacta OB1,
                   G02 promete OB1 (500 al 30-oct, aún no evaluable al corte).
    """
    clientes = pd.DataFrame(
        {
            "id_cliente": ["C1", "C2", "C3"],
            "documento": ["10010001", "10020002", "10030003"],
            "nombre": ["Ana", "Beto", "Caro"],
            "ciudad": ["Bogotá", "Cali", "Medellín"],
            "segmento": ["Masivo"] * 3,
            "fecha_vinculacion": [ts("2020-01-01")] * 3,
        }
    )
    obligaciones = pd.DataFrame(
        {
            "id_obligacion": ["OB1", "OB2", "OB3"],
            "id_cliente": ["C1", "C2", "C3"],
            "producto": ["Tarjeta de crédito", "Libre inversión", "Microcrédito"],
            "monto_desembolsado": [5000.0, 8000.0, 9000.0],
            "plazo_meses": pd.array([24, 36, 12], dtype="Int64"),
            "tasa_mensual": [0.02, 0.015, 0.03],
            "fecha_desembolso": [ts("2025-01-15")] * 3,
        }
    )
    gestores = pd.DataFrame(
        {
            "id_gestor": ["G01", "G02"],
            "nombre": ["Gestor Uno", "Gestor Dos"],
            "equipo": ["Temprana"] * 2,
        }
    )
    cortes = pd.DataFrame(
        {
            "id_obligacion": ["OB1", "OB2", "OB3", "OB1", "OB2"],
            "fecha_corte": [ts("2026-09-30")] * 3 + [ts("2026-10-31")] * 2,
            "saldo_capital": [1000.0, 2000.0, 3000.0, 1000.0, 1500.0],
            "dias_mora": pd.array([0, 45, 100, 10, 0], dtype="Int64"),
        }
    )
    pagos = pd.DataFrame(
        {
            "id_pago": ["P1", "P2"],
            "id_obligacion": ["OB3", "OB2"],
            "fecha_pago": [ts("2026-09-10"), ts("2026-10-15")],
            "valor": [100.0, 600.0],
            "canal": ["PSE", "Oficina"],
        }
    )
    gestiones = pd.DataFrame(
        {
            "id_gestion": ["GS1", "GS2", "GS3"],
            "id_obligacion": ["OB2", "OB1", "OB1"],
            "id_gestor": ["G01", "G01", "G02"],
            "fecha_gestion": [
                ts("2026-10-10 09:00"),
                ts("2026-10-20 10:00"),
                ts("2026-10-29 11:00"),
            ],
            "canal": ["Llamada", "Llamada", "WhatsApp"],
            "resultado": ["Promesa de pago", "No contesta", "Promesa de pago"],
            "fecha_promesa": [ts("2026-10-14"), pd.NaT, ts("2026-10-30")],
            "valor_promesa": [600.0, float("nan"), 500.0],
        }
    )
    return RawData(clientes, obligaciones, gestores, cortes, pagos, gestiones)


@pytest.fixture
def tiny_model() -> StarSchema:
    return build_model(tiny_data(), AS_OF)


@pytest.fixture(scope="session")
def synthetic() -> SyntheticData:
    clean = generate(SyntheticConfig(seed=7, clients=400, months=4))
    return dirty_exports(clean, seed=7)


@pytest.fixture(scope="session")
def raw_dir(tmp_path_factory: pytest.TempPathFactory, synthetic: SyntheticData) -> Path:
    path = tmp_path_factory.mktemp("raw")
    write_raw(synthetic, path)
    return path


@pytest.fixture(scope="session")
def pipeline_run(
    tmp_path_factory: pytest.TempPathFactory, raw_dir: Path
) -> tuple[PipelineResult, Path, str]:
    out = tmp_path_factory.mktemp("reports")
    db_url = f"sqlite:///{(tmp_path_factory.mktemp('dw') / 'dw.db').as_posix()}"
    return run_pipeline(raw_dir, out, database_url=db_url), out, db_url
