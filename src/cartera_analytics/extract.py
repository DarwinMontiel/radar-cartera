"""Extracción: lee los exportes de los sistemas de origen sin interpretar tipos todavía.

Todo se lee como texto (o el tipo nativo de Excel) para que la limpieza sea explícita y
auditable: nada de inferencias silenciosas que conviertan un documento ``0012345`` en ``12345``.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path

import pandas as pd


@dataclass
class RawData:
    clientes: pd.DataFrame
    obligaciones: pd.DataFrame
    gestores: pd.DataFrame
    cortes: pd.DataFrame
    pagos: pd.DataFrame
    gestiones: pd.DataFrame

    def row_counts(self) -> dict[str, int]:
        return {f.name: len(getattr(self, f.name)) for f in fields(self)}


class SourceError(FileNotFoundError):
    """Falta un archivo de origen obligatorio."""


def _csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise SourceError(f"No se encontró el archivo de origen: {path}")
    return pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""], encoding="utf-8")


def read_raw(raw_dir: Path) -> RawData:
    cut_files = sorted((raw_dir / "cartera").glob("corte_*.csv"))
    if not cut_files:
        raise SourceError(f"No hay cortes de cartera en {raw_dir / 'cartera'}")
    cortes = pd.concat([_csv(p).assign(archivo=p.name) for p in cut_files], ignore_index=True)

    pagos_path = raw_dir / "pagos.xlsx"
    if not pagos_path.exists():
        raise SourceError(f"No se encontró el archivo de origen: {pagos_path}")
    pagos = pd.read_excel(
        pagos_path, sheet_name="Recaudo", dtype={"id_pago": str, "id_obligacion": str}
    )

    return RawData(
        clientes=_csv(raw_dir / "clientes.csv"),
        obligaciones=_csv(raw_dir / "obligaciones.csv"),
        gestores=_csv(raw_dir / "gestores.csv"),
        cortes=cortes,
        pagos=pagos,
        gestiones=_csv(raw_dir / "gestiones.csv"),
    )
