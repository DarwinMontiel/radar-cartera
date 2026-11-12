"""CLI ``cartera``: generar datos de ejemplo, ejecutar el pipeline e inspeccionar el esquema."""

from __future__ import annotations

import logging
import os
from datetime import date, datetime
from pathlib import Path

import typer

from radar_cartera.pipeline import run_pipeline
from radar_cartera.synthetic import SyntheticConfig, dirty_exports, generate, write_raw
from radar_cartera.warehouse import ddl

app = typer.Typer(help="ETL y analítica de cartera y cobranzas.", no_args_is_help=True)


def _date(value: str | None) -> date | None:
    return datetime.strptime(value, "%Y-%m-%d").date() if value else None


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v", help="Logs detallados.")) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


@app.command("generate")
def generate_cmd(
    out: Path = typer.Option(Path("data/raw"), help="Carpeta donde escribir los exportes."),
    seed: int = typer.Option(42, help="Semilla (misma semilla = mismos datos)."),
    clients: int = typer.Option(1500, min=50, help="Número de clientes."),
    months: int = typer.Option(12, min=3, max=36, help="Número de cortes mensuales."),
    last_cut: str = typer.Option("2026-10-31", help="Último corte (AAAA-MM-DD)."),
    clean: bool = typer.Option(False, help="No inyectar problemas de calidad."),
) -> None:
    """Genera exportes sintéticos (CSV + Excel) con problemas de calidad realistas."""
    cfg = SyntheticConfig(seed=seed, clients=clients, months=months, last_cut=_date(last_cut))  # type: ignore[arg-type]
    data = generate(cfg)
    if not clean:
        data = dirty_exports(data, seed)
    files = write_raw(data, out)
    typer.echo(f"{len(files)} archivos en {out}")
    for kind, count in data.anomalies.items():
        typer.echo(f"  · anomalía inyectada {kind}: {count}")


@app.command("run")
def run_cmd(
    raw: Path = typer.Option(
        Path("data/raw"), exists=True, file_okay=False, help="Exportes de origen."
    ),
    out: Path = typer.Option(Path("reports"), help="Carpeta de salida de reportes."),
    db: str | None = typer.Option(
        None, help="URL SQLAlchemy del DW (o variable CARTERA_DATABASE_URL). Sin URL no se carga."
    ),
    as_of: str | None = typer.Option(None, help="Fecha de corte (por defecto, el último corte)."),
) -> None:
    """Ejecuta el pipeline completo y escribe Excel, HTML, rechazados y manifiesto."""
    result = run_pipeline(raw, out, _date(as_of), db or os.getenv("CARTERA_DATABASE_URL"))
    assert result.quality is not None
    assert result.kpis is not None
    latest = result.kpis.latest
    typer.echo(f"Ejecución {result.run_id} · corte {result.kpis.month}")
    typer.echo(f"  Registros rechazados: {result.quality.total_rejected}")
    typer.echo(f"  Saldo total: $ {latest['saldo_total']:,.0f} · PAR30 {latest['par30']:.1%}")
    typer.echo(f"  Recaudo del mes: $ {latest['recaudo']:,.0f}")
    if result.rows_loaded:
        typer.echo(f"  Cargado al DW: {sum(result.rows_loaded.values()):,} filas")
    typer.echo(f"  Reportes en {out.resolve()}")


@app.command("ddl")
def ddl_cmd(dialect: str = typer.Option("postgresql", help="postgresql | sqlite")) -> None:
    """Imprime el DDL del data warehouse para el dialecto indicado."""
    typer.echo(ddl(dialect))


if __name__ == "__main__":
    app()
