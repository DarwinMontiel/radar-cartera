"""KPIs de cartera y cobranza calculados sobre el modelo estrella.

Las definiciones están documentadas en ``docs/kpis.md`` y son las mismas que implementan las
vistas SQL (``sql/views.sql``) y las medidas DAX (``powerbi/medidas.dax``). Una prueba
automática verifica que pandas y SQL producen exactamente los mismos números.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from cartera_analytics.domain import BUCKETS, SALIDA
from cartera_analytics.model import StarSchema
from cartera_analytics.transform import safe_ratio


@dataclass
class KpiBundle:
    month: str
    monthly: pd.DataFrame
    buckets: pd.DataFrame
    roll_counts: pd.DataFrame
    roll_rates: pd.DataFrame
    ranking: pd.DataFrame
    by_product: pd.DataFrame
    by_channel: pd.DataFrame

    @property
    def latest(self) -> pd.Series:
        return self.monthly.loc[self.monthly["anio_mes"] == self.month].iloc[0]


def _with_month(fact: pd.DataFrame, dim_fecha: pd.DataFrame, key: str) -> pd.DataFrame:
    months = dim_fecha.set_index("fecha_key")["anio_mes"]
    return fact.assign(anio_mes=fact[key].map(months))


def monthly_kpis(model: StarSchema) -> pd.DataFrame:
    cartera = _with_month(model.fact_cartera, model.dim_fecha, "corte_key")
    saldo = cartera["saldo_capital"]
    cartera = cartera.assign(
        saldo_vencido=saldo.where(cartera["dias_mora"] > 0, 0.0),
        saldo_mora_30=saldo.where(cartera["dias_mora"] > 30, 0.0),
        saldo_mora_90=saldo.where(cartera["dias_mora"] > 90, 0.0),
    )
    base = (
        cartera.groupby("anio_mes")
        .agg(
            obligaciones=("obligacion_key", "size"),
            saldo_total=("saldo_capital", "sum"),
            saldo_vencido=("saldo_vencido", "sum"),
            obligaciones_mora=("en_mora", "sum"),
            saldo_mora_30=("saldo_mora_30", "sum"),
            saldo_mora_90=("saldo_mora_90", "sum"),
        )
        .sort_index()
    )

    pagos = _with_month(model.fact_pagos, model.dim_fecha, "fecha_key")
    recaudo = pagos.groupby("anio_mes")["valor"].sum()

    gestiones = _with_month(model.fact_gestiones, model.dim_fecha, "fecha_key")
    gest = gestiones.groupby("anio_mes").agg(
        gestiones=("id_gestion", "size"), contactos=("es_contacto", "sum")
    )

    promesas = _with_month(model.fact_promesas, model.dim_fecha, "fecha_promesa_key")
    evaluables = promesas[promesas["evaluable"]]
    prom = evaluables.groupby("anio_mes").agg(
        promesas_evaluables=("id_gestion", "size"), promesas_cumplidas=("cumplida", "sum")
    )

    out = base.join(recaudo.rename("recaudo")).join(gest).join(prom)
    out[["recaudo"]] = out[["recaudo"]].fillna(0.0)
    count_cols = ["gestiones", "contactos", "promesas_evaluables", "promesas_cumplidas"]
    out[count_cols] = out[count_cols].fillna(0).astype("int64")
    out["obligaciones_mora"] = out["obligaciones_mora"].astype("int64")

    out["par30"] = safe_ratio(out["saldo_mora_30"], out["saldo_total"])
    out["par90"] = safe_ratio(out["saldo_mora_90"], out["saldo_total"])
    out["tasa_recuperacion"] = safe_ratio(out["recaudo"], out["saldo_vencido"].shift(1))
    out["contactabilidad"] = safe_ratio(out["contactos"], out["gestiones"])
    out["efectividad_promesas"] = safe_ratio(out["promesas_cumplidas"], out["promesas_evaluables"])
    out["recaudo_var_mensual"] = safe_ratio(out["recaudo"], out["recaudo"].shift(1)) - 1
    return out.drop(columns=["saldo_mora_30", "saldo_mora_90"]).reset_index()


def portfolio_by_bucket(model: StarSchema) -> pd.DataFrame:
    cartera = _with_month(model.fact_cartera, model.dim_fecha, "corte_key")
    pivot = cartera.pivot_table(
        index="anio_mes",
        columns="bucket_mora",
        values="saldo_capital",
        aggfunc="sum",
        fill_value=0.0,
    )
    return pivot.reindex(columns=BUCKETS, fill_value=0.0).reset_index()


def roll_rates(model: StarSchema, month: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Matriz de transición entre franjas del corte anterior y el corte ``month``.

    Filas = franja de origen, columnas = franja de destino (o salida de cartera).
    Devuelve (conteos, proporciones por fila).
    """
    cartera = _with_month(model.fact_cartera, model.dim_fecha, "corte_key")
    months = sorted(cartera["anio_mes"].unique())
    month = month or months[-1]
    idx = months.index(month)
    if idx == 0:
        raise ValueError("El primer corte no tiene corte anterior para calcular roll rates")
    origin = cartera[cartera["anio_mes"] == months[idx - 1]][["obligacion_key", "bucket_mora"]]
    dest = cartera[cartera["anio_mes"] == month][["obligacion_key", "bucket_mora"]]
    pairs = origin.merge(dest, on="obligacion_key", how="left", suffixes=("_origen", "_destino"))
    pairs["bucket_mora_destino"] = pairs["bucket_mora_destino"].fillna(SALIDA)

    counts = pd.crosstab(pairs["bucket_mora_origen"], pairs["bucket_mora_destino"])
    counts = counts.reindex(index=BUCKETS, columns=[*BUCKETS, SALIDA], fill_value=0)
    counts.index.name, counts.columns.name = "origen", "destino"
    totals = counts.sum(axis=1)
    rates = counts.div(totals.where(totals > 0), axis=0).fillna(0.0)
    return counts, rates


def collector_ranking(model: StarSchema, month: str) -> pd.DataFrame:
    """Ranking de gestores del mes (por fecha de gestión) según recaudo de promesas cumplidas."""
    gestiones = _with_month(model.fact_gestiones, model.dim_fecha, "fecha_key")
    gestiones = gestiones[gestiones["anio_mes"] == month]
    activity = gestiones.groupby("gestor_key").agg(
        gestiones=("id_gestion", "size"),
        contactos=("es_contacto", "sum"),
        promesas=("es_promesa", "sum"),
    )
    promesas = _with_month(model.fact_promesas, model.dim_fecha, "fecha_gestion_key")
    promesas = promesas[promesas["anio_mes"] == month]
    cumplidas = promesas[promesas["cumplida"]]
    results = cumplidas.groupby("gestor_key").agg(
        promesas_cumplidas=("id_gestion", "size"), recaudo_promesas=("valor_pagado", "sum")
    )
    evaluables = promesas[promesas["evaluable"]].groupby("gestor_key").size().rename("evaluables")

    out = (
        model.dim_gestor.set_index("gestor_key")[["id_gestor", "nombre", "equipo"]]
        .join(activity, how="inner")
        .join(results)
        .join(evaluables)
    )
    out["promesas_cumplidas"] = out["promesas_cumplidas"].fillna(0).astype("int64")
    out["recaudo_promesas"] = out["recaudo_promesas"].fillna(0.0)
    out["evaluables"] = out["evaluables"].fillna(0).astype("int64")
    out["contactabilidad"] = safe_ratio(out["contactos"], out["gestiones"])
    out["efectividad_promesas"] = safe_ratio(out["promesas_cumplidas"], out["evaluables"])
    out["ranking"] = out["recaudo_promesas"].rank(method="dense", ascending=False).astype("int64")
    out = out.drop(columns=["evaluables"]).reset_index()
    return out.sort_values(["ranking", "id_gestor"], ignore_index=True)


def portfolio_by_product(model: StarSchema, month: str) -> pd.DataFrame:
    cartera = _with_month(model.fact_cartera, model.dim_fecha, "corte_key")
    cartera = cartera[cartera["anio_mes"] == month].merge(
        model.dim_obligacion[["obligacion_key", "producto"]], on="obligacion_key"
    )
    cartera["saldo_mora_30"] = cartera["saldo_capital"].where(cartera["dias_mora"] > 30, 0.0)
    out = cartera.groupby("producto").agg(
        obligaciones=("obligacion_key", "size"),
        saldo_total=("saldo_capital", "sum"),
        saldo_mora_30=("saldo_mora_30", "sum"),
    )
    out["par30"] = safe_ratio(out["saldo_mora_30"], out["saldo_total"])
    return (
        out.drop(columns="saldo_mora_30").sort_values("saldo_total", ascending=False).reset_index()
    )


def collections_by_channel(model: StarSchema, month: str) -> pd.DataFrame:
    pagos = _with_month(model.fact_pagos, model.dim_fecha, "fecha_key")
    pagos = pagos[pagos["anio_mes"] == month]
    out = pagos.groupby("canal_pago").agg(pagos=("id_pago", "size"), recaudo=("valor", "sum"))
    out["participacion"] = safe_ratio(
        out["recaudo"], pd.Series(out["recaudo"].sum(), index=out.index)
    )
    return out.sort_values("recaudo", ascending=False).reset_index()


def compute_all(model: StarSchema, month: str | None = None) -> KpiBundle:
    monthly = monthly_kpis(model)
    month = month or str(monthly["anio_mes"].iloc[-1])
    counts, rates = roll_rates(model, month)
    return KpiBundle(
        month=month,
        monthly=monthly,
        buckets=portfolio_by_bucket(model),
        roll_counts=counts,
        roll_rates=rates,
        ranking=collector_ranking(model, month),
        by_product=portfolio_by_product(model, month),
        by_channel=collections_by_channel(model, month),
    )
