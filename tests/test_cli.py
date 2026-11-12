"""CLI ``cartera`` con ``typer.testing.CliRunner``: salida en español y formato colombiano."""

from __future__ import annotations

import re
from pathlib import Path

from typer.testing import CliRunner

from radar_cartera.cli import app

runner = CliRunner()


def test_generate_and_run_print_colombian_formats(tmp_path: Path) -> None:
    raw, out = tmp_path / "raw", tmp_path / "out"
    generated = runner.invoke(
        app, ["generate", "--out", str(raw), "--clients", "80", "--months", "3", "--seed", "5"]
    )
    assert generated.exit_code == 0, generated.output
    assert "anomalía inyectada pagos_duplicados" in generated.output

    result = runner.invoke(app, ["run", "--raw", str(raw), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert "corte 2026-10" in result.output
    # $ 1.234.567 (punto de miles, sin decimales) y 9,3 % (coma decimal, espacio antes de %).
    assert re.search(r"Saldo total: \$ \d{1,3}(\.\d{3})+ · PAR30 \d+,\d %", result.output)
    assert re.search(r"Recaudo del mes: \$ \d{1,3}(\.\d{3})*\n", result.output)
    assert "," not in result.output.split("Saldo total: ")[1].split(" · ")[0]
    assert (out / "reporte_cartera_2026-10.xlsx").exists()

    past = runner.invoke(
        app, ["run", "--raw", str(raw), "--out", str(tmp_path / "sep"), "--as-of", "2026-09-30"]
    )
    assert past.exit_code == 0, past.output
    assert "corte 2026-09" in past.output
    assert "Fuera de alcance (posteriores al 2026-09-30)" in past.output


def test_run_rejects_malformed_date(tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", "--raw", str(tmp_path), "--as-of", "30/09/2026"])
    assert result.exit_code == 2
    assert "AAAA-MM-DD" in result.output


def test_run_reports_missing_sources_without_traceback(tmp_path: Path) -> None:
    result = runner.invoke(app, ["run", "--raw", str(tmp_path), "--out", str(tmp_path / "o")])
    assert result.exit_code == 1
    assert "No hay cortes de cartera" in result.output
    assert "Traceback" not in result.output


def test_run_explains_an_as_of_without_previous_cut(tmp_path: Path) -> None:
    raw = tmp_path / "raw"
    runner.invoke(app, ["generate", "--out", str(raw), "--clients", "60", "--months", "3"])
    result = runner.invoke(
        app, ["run", "--raw", str(raw), "--out", str(tmp_path / "o"), "--as-of", "2026-08-31"]
    )
    assert result.exit_code == 1
    assert "corte anterior" in result.output


def test_ddl_command_and_unknown_dialect() -> None:
    ok = runner.invoke(app, ["ddl", "--dialect", "sqlite"])
    assert ok.exit_code == 0
    assert "CREATE TABLE fact_cartera" in ok.output
    bad = runner.invoke(app, ["ddl", "--dialect", "oracle"])
    assert bad.exit_code == 1
    assert "dialecto desconocido" in bad.output
