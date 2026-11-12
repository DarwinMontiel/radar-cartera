"""Carga del modelo estrella al data warehouse (PostgreSQL en producción, SQLite en pruebas).

Estrategia: *full refresh* transaccional e idempotente. Dentro de una sola transacción se
eliminan las vistas, se vacían hechos y dimensiones, se insertan los datos nuevos y se recrean
las vistas para Power BI. Si algo falla, la base queda exactamente como estaba (ver ADR-0002).
"""

from __future__ import annotations

from importlib import resources

import pandas as pd
from sqlalchemy import (
    Boolean,
    Column,
    Connection,
    Date,
    Engine,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    PrimaryKeyConstraint,
    String,
    Table,
    delete,
    text,
)
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.engine import Dialect
from sqlalchemy.schema import CreateIndex, CreateTable

from radar_cartera.model import StarSchema

metadata = MetaData()
MONEY = Numeric(18, 2)

dim_fecha = Table(
    "dim_fecha", metadata,
    Column("fecha_key", Integer, primary_key=True, autoincrement=False),
    Column("fecha", Date, nullable=False, unique=True),
    Column("anio", Integer, nullable=False),
    Column("mes", Integer, nullable=False),
    Column("dia", Integer, nullable=False),
    Column("anio_mes", String(7), nullable=False, index=True),
    Column("nombre_mes", String(12), nullable=False),
    Column("trimestre", String(2), nullable=False),
    Column("dia_semana", String(10), nullable=False),
    Column("es_fin_de_semana", Boolean, nullable=False),
    Column("es_fin_de_mes", Boolean, nullable=False),
)  # fmt: skip

dim_cliente = Table(
    "dim_cliente", metadata,
    Column("cliente_key", Integer, primary_key=True, autoincrement=False),
    Column("id_cliente", String(16), nullable=False, unique=True),
    Column("documento", String(12), nullable=False),
    Column("nombre", String(120), nullable=False),
    Column("ciudad", String(40), nullable=False),
    Column("segmento", String(20), nullable=False),
    Column("fecha_vinculacion", Date),
)  # fmt: skip

dim_obligacion = Table(
    "dim_obligacion", metadata,
    Column("obligacion_key", Integer, primary_key=True, autoincrement=False),
    Column("id_obligacion", String(16), nullable=False, unique=True),
    Column("cliente_key", Integer, ForeignKey("dim_cliente.cliente_key"), nullable=False),
    Column("producto", String(40), nullable=False),
    Column("monto_desembolsado", MONEY, nullable=False),
    Column("plazo_meses", Integer, nullable=False),
    Column("tasa_mensual", Float, nullable=False),
    Column("fecha_desembolso", Date, nullable=False),
)  # fmt: skip

dim_gestor = Table(
    "dim_gestor", metadata,
    Column("gestor_key", Integer, primary_key=True, autoincrement=False),
    Column("id_gestor", String(8), nullable=False, unique=True),
    Column("nombre", String(80), nullable=False),
    Column("equipo", String(20), nullable=False),
)  # fmt: skip

fact_cartera = Table(
    "fact_cartera", metadata,
    Column("corte_key", Integer, ForeignKey("dim_fecha.fecha_key"), nullable=False),
    Column("obligacion_key", Integer, ForeignKey("dim_obligacion.obligacion_key"), nullable=False),
    Column("cliente_key", Integer, ForeignKey("dim_cliente.cliente_key"), nullable=False),
    Column("saldo_capital", MONEY, nullable=False),
    Column("dias_mora", Integer, nullable=False),
    Column("bucket_mora", String(10), nullable=False),
    Column("en_mora", Boolean, nullable=False),
    PrimaryKeyConstraint("corte_key", "obligacion_key"),
)  # fmt: skip

fact_pagos = Table(
    "fact_pagos", metadata,
    Column("id_pago", String(16), primary_key=True),
    Column("fecha_key", Integer, ForeignKey("dim_fecha.fecha_key"), nullable=False),
    Column("obligacion_key", Integer, ForeignKey("dim_obligacion.obligacion_key"), nullable=False),
    Column("cliente_key", Integer, ForeignKey("dim_cliente.cliente_key"), nullable=False),
    Column("valor", MONEY, nullable=False),
    Column("canal_pago", String(40), nullable=False),
    Index("ix_fact_pagos_fecha", "fecha_key"),
)  # fmt: skip

fact_gestiones = Table(
    "fact_gestiones", metadata,
    Column("id_gestion", String(16), primary_key=True),
    Column("fecha_key", Integer, ForeignKey("dim_fecha.fecha_key"), nullable=False),
    Column("obligacion_key", Integer, ForeignKey("dim_obligacion.obligacion_key"), nullable=False),
    Column("gestor_key", Integer, ForeignKey("dim_gestor.gestor_key"), nullable=False),
    Column("canal", String(20), nullable=False),
    Column("resultado", String(30), nullable=False),
    Column("es_contacto", Boolean, nullable=False),
    Column("es_promesa", Boolean, nullable=False),
    Index("ix_fact_gestiones_fecha", "fecha_key"),
)  # fmt: skip

fact_promesas = Table(
    "fact_promesas", metadata,
    Column("id_gestion", String(16), primary_key=True),
    Column("fecha_gestion_key", Integer, ForeignKey("dim_fecha.fecha_key"), nullable=False),
    Column("fecha_promesa_key", Integer, ForeignKey("dim_fecha.fecha_key"), nullable=False),
    Column("obligacion_key", Integer, ForeignKey("dim_obligacion.obligacion_key"), nullable=False),
    Column("gestor_key", Integer, ForeignKey("dim_gestor.gestor_key"), nullable=False),
    Column("valor_prometido", MONEY, nullable=False),
    Column("valor_pagado", MONEY, nullable=False),
    Column("evaluable", Boolean, nullable=False),
    Column("cumplida", Boolean, nullable=False),
)  # fmt: skip

LOAD_ORDER = [
    dim_fecha, dim_cliente, dim_obligacion, dim_gestor,
    fact_cartera, fact_pagos, fact_gestiones, fact_promesas,
]  # fmt: skip
VIEWS = ["vw_kpi_mensual", "vw_cartera_franja", "vw_roll_rate", "vw_ranking_gestores"]


def views_sql() -> list[str]:
    script = resources.files("radar_cartera").joinpath("sql/views.sql").read_text("utf-8")
    statements = [s.strip() for s in script.split(";")]
    return [
        s for s in statements if s and not all(line.startswith("--") for line in s.splitlines())
    ]


DIALECTS: dict[str, Dialect] = {
    "postgresql": postgresql.dialect(),  # type: ignore[no-untyped-call]
    "sqlite": sqlite.dialect(),
}


def ddl(dialect: str = "postgresql") -> str:
    """DDL del esquema para el dialecto dado (documentación y revisión con el DBA)."""
    target = DIALECTS[dialect]
    parts = []
    for table in metadata.sorted_tables:
        parts.append(str(CreateTable(table).compile(dialect=target)).strip() + ";")
        parts.extend(
            str(CreateIndex(idx).compile(dialect=target)).strip() + ";" for idx in table.indexes
        )
    return "\n\n".join(parts) + "\n"


def _drop_views(conn: Connection) -> None:
    for view in reversed(VIEWS):
        conn.execute(text(f"DROP VIEW IF EXISTS {view}"))


def load(model: StarSchema, engine: Engine) -> dict[str, int]:
    """Carga completa e idempotente. Devuelve filas insertadas por tabla."""
    frames = model.tables()
    with engine.begin() as conn:
        _drop_views(conn)
        metadata.create_all(conn)
        for table in reversed(LOAD_ORDER):
            conn.execute(delete(table))
        counts = {}
        for table in LOAD_ORDER:
            frame = frames[table.name]
            frame.to_sql(
                table.name, conn, if_exists="append", index=False, method="multi", chunksize=500
            )
            counts[table.name] = len(frame)
        for statement in views_sql():
            conn.execute(text(statement))
    return counts


def read_view(engine: Engine, view: str) -> pd.DataFrame:
    if view not in VIEWS:
        raise ValueError(f"Vista desconocida: {view}")
    return pd.read_sql(text(f"SELECT * FROM {view}"), engine)  # noqa: S608 - lista blanca
