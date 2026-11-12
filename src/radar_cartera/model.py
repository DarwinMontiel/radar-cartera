"""Modelo dimensional (esquema estrella) listo para el data warehouse y Power BI.

Dimensiones: fecha, cliente, obligación, gestor.
Hechos: cartera mensual (snapshot por corte), pagos, gestiones y promesas de pago.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date

import numpy as np
import pandas as pd

from radar_cartera.domain import (
    DIAS,
    MESES,
    PROMESA_DIAS_GRACIA,
    PROMESA_PORCENTAJE_MINIMO,
    RESULTADO_PROMESA,
    RESULTADOS_CONTACTO,
)
from radar_cartera.extract import RawData
from radar_cartera.transform import aging_bucket


@dataclass
class StarSchema:
    dim_fecha: pd.DataFrame
    dim_cliente: pd.DataFrame
    dim_obligacion: pd.DataFrame
    dim_gestor: pd.DataFrame
    fact_cartera: pd.DataFrame
    fact_pagos: pd.DataFrame
    fact_gestiones: pd.DataFrame
    fact_promesas: pd.DataFrame

    def tables(self) -> dict[str, pd.DataFrame]:
        """Tablas en orden de carga (dimensiones antes que hechos)."""
        return {f.name: getattr(self, f.name) for f in fields(self)}


def date_key(values: pd.Series) -> pd.Series:
    return values.dt.strftime("%Y%m%d").astype("int64")


def build_dim_fecha(start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    days = pd.date_range(start.normalize(), end.normalize(), freq="D")
    frame = pd.DataFrame({"fecha": days})
    return pd.DataFrame(
        {
            "fecha_key": date_key(frame["fecha"]),
            "fecha": frame["fecha"].dt.date,
            "anio": frame["fecha"].dt.year,
            "mes": frame["fecha"].dt.month,
            "dia": frame["fecha"].dt.day,
            "anio_mes": frame["fecha"].dt.strftime("%Y-%m"),
            "nombre_mes": [MESES[m - 1] for m in frame["fecha"].dt.month],
            "trimestre": "T" + frame["fecha"].dt.quarter.astype(str),
            "dia_semana": [DIAS[d] for d in frame["fecha"].dt.day_of_week],
            "es_fin_de_semana": frame["fecha"].dt.day_of_week >= 5,
            "es_fin_de_mes": frame["fecha"].dt.is_month_end,
        }
    )


def _surrogate(ids: pd.Series) -> dict[str, int]:
    return {value: i for i, value in enumerate(sorted(ids.unique()), start=1)}


def evaluate_promises(
    gestiones: pd.DataFrame,
    pagos: pd.DataFrame,
    as_of: date,
    grace_days: int = PROMESA_DIAS_GRACIA,
    min_ratio: float = PROMESA_PORCENTAJE_MINIMO,
) -> pd.DataFrame:
    """Calcula, para cada promesa, lo pagado en su ventana y si se cumplió.

    Ventana: desde el día de la gestión hasta ``fecha_promesa + grace_days``. Una promesa es
    *evaluable* solo si su ventana ya cerró al corte ``as_of``; las demás quedan pendientes.

    Atribución (último toque): cada pago cuenta para **una sola** promesa. Si cae en la ventana
    de varias promesas de la misma obligación, se atribuye a la gestión más reciente anterior al
    pago (empate: el ``id_gestion`` mayor). Así un mismo peso no se cuenta dos veces en la
    efectividad ni en el ranking de gestores.
    """
    promesas = gestiones.loc[
        gestiones["resultado"] == RESULTADO_PROMESA,
        [
            "id_gestion",
            "id_obligacion",
            "id_gestor",
            "fecha_gestion",
            "fecha_promesa",
            "valor_promesa",
        ],
    ].copy()
    promesas["inicio"] = promesas["fecha_gestion"].dt.normalize()
    promesas["fin"] = promesas["fecha_promesa"] + pd.Timedelta(days=grace_days)

    cruce = promesas[["id_gestion", "id_obligacion", "fecha_gestion", "inicio", "fin"]].merge(
        pagos[["id_pago", "id_obligacion", "fecha_pago", "valor"]], on="id_obligacion"
    )
    cruce = cruce[cruce["fecha_pago"].between(cruce["inicio"], cruce["fin"])]
    atribuidos = cruce.sort_values(["fecha_gestion", "id_gestion"], kind="stable").drop_duplicates(
        "id_pago", keep="last"
    )
    pagado = atribuidos.groupby("id_gestion")["valor"].sum()

    promesas["valor_pagado"] = promesas["id_gestion"].map(pagado).fillna(0.0)
    promesas["evaluable"] = promesas["fin"] <= pd.Timestamp(as_of)
    promesas["cumplida"] = promesas["evaluable"] & (
        promesas["valor_pagado"] >= min_ratio * promesas["valor_promesa"]
    )
    return promesas.drop(columns=["inicio", "fin"])


def build_model(data: RawData, as_of: date) -> StarSchema:
    clientes, obligaciones = data.clientes, data.obligaciones
    cliente_key = _surrogate(clientes["id_cliente"])
    obligacion_key = _surrogate(obligaciones["id_obligacion"])
    gestor_key = _surrogate(data.gestores["id_gestor"])
    ob_cliente = obligaciones.set_index("id_obligacion")["id_cliente"].map(cliente_key)

    dim_cliente = pd.DataFrame(
        {
            "cliente_key": clientes["id_cliente"].map(cliente_key).astype("int64"),
            "id_cliente": clientes["id_cliente"],
            "documento": clientes["documento"],
            "nombre": clientes["nombre"],
            "ciudad": clientes["ciudad"].fillna("Sin ciudad"),
            "segmento": clientes["segmento"],
            "fecha_vinculacion": clientes["fecha_vinculacion"].dt.date,
        }
    ).sort_values("cliente_key", ignore_index=True)

    dim_obligacion = pd.DataFrame(
        {
            "obligacion_key": obligaciones["id_obligacion"].map(obligacion_key).astype("int64"),
            "id_obligacion": obligaciones["id_obligacion"],
            "cliente_key": obligaciones["id_cliente"].map(cliente_key).astype("int64"),
            "producto": obligaciones["producto"],
            "monto_desembolsado": obligaciones["monto_desembolsado"],
            "plazo_meses": obligaciones["plazo_meses"].astype("int64"),
            "tasa_mensual": obligaciones["tasa_mensual"],
            "fecha_desembolso": obligaciones["fecha_desembolso"].dt.date,
        }
    ).sort_values("obligacion_key", ignore_index=True)

    dim_gestor = pd.DataFrame(
        {
            "gestor_key": data.gestores["id_gestor"].map(gestor_key).astype("int64"),
            "id_gestor": data.gestores["id_gestor"],
            "nombre": data.gestores["nombre"],
            "equipo": data.gestores["equipo"],
        }
    ).sort_values("gestor_key", ignore_index=True)

    cortes = data.cortes
    fact_cartera = pd.DataFrame(
        {
            "corte_key": date_key(cortes["fecha_corte"]),
            "obligacion_key": cortes["id_obligacion"].map(obligacion_key).astype("int64"),
            "cliente_key": cortes["id_obligacion"].map(ob_cliente).astype("int64"),
            "saldo_capital": cortes["saldo_capital"],
            "dias_mora": cortes["dias_mora"].astype("int64"),
            "bucket_mora": aging_bucket(cortes["dias_mora"].astype("int64")).astype(str),
            "en_mora": cortes["dias_mora"] > 0,
        }
    ).sort_values(["corte_key", "obligacion_key"], ignore_index=True)

    pagos = data.pagos
    fact_pagos = pd.DataFrame(
        {
            "id_pago": pagos["id_pago"],
            "fecha_key": date_key(pagos["fecha_pago"]),
            "obligacion_key": pagos["id_obligacion"].map(obligacion_key).astype("int64"),
            "cliente_key": pagos["id_obligacion"].map(ob_cliente).astype("int64"),
            "valor": pagos["valor"],
            "canal_pago": pagos["canal"],
        }
    ).sort_values("id_pago", ignore_index=True)

    gestiones = data.gestiones
    fact_gestiones = pd.DataFrame(
        {
            "id_gestion": gestiones["id_gestion"],
            "fecha_key": date_key(gestiones["fecha_gestion"]),
            "obligacion_key": gestiones["id_obligacion"].map(obligacion_key).astype("int64"),
            "gestor_key": gestiones["id_gestor"].map(gestor_key).astype("int64"),
            "canal": gestiones["canal"],
            "resultado": gestiones["resultado"],
            "es_contacto": gestiones["resultado"].isin(RESULTADOS_CONTACTO).astype(bool),
            "es_promesa": (gestiones["resultado"] == RESULTADO_PROMESA).astype(bool),
        }
    ).sort_values("id_gestion", ignore_index=True)

    promesas = evaluate_promises(gestiones, pagos, as_of)
    fact_promesas = pd.DataFrame(
        {
            "id_gestion": promesas["id_gestion"],
            "fecha_gestion_key": date_key(promesas["fecha_gestion"]),
            "fecha_promesa_key": date_key(promesas["fecha_promesa"]),
            "obligacion_key": promesas["id_obligacion"].map(obligacion_key).astype("int64"),
            "gestor_key": promesas["id_gestor"].map(gestor_key).astype("int64"),
            "valor_prometido": promesas["valor_promesa"],
            "valor_pagado": promesas["valor_pagado"],
            "evaluable": promesas["evaluable"].astype(bool),
            "cumplida": promesas["cumplida"].astype(bool),
        }
    ).sort_values("id_gestion", ignore_index=True)

    all_dates = pd.concat(
        [
            cortes["fecha_corte"],
            pagos["fecha_pago"],
            gestiones["fecha_gestion"].dt.normalize(),
            promesas["fecha_promesa"],
        ]
    )
    dim_fecha = build_dim_fecha(all_dates.min(), max(all_dates.max(), pd.Timestamp(as_of)))

    # Las reglas de calidad garantizan integridad referencial; esto protege contra regresiones.
    for fact, key in ((fact_cartera, "corte_key"), (fact_pagos, "fecha_key")):
        if not np.isin(fact[key], dim_fecha["fecha_key"]).all():  # pragma: no cover
            raise ValueError(f"Hay fechas sin dimensión en {key}")

    return StarSchema(
        dim_fecha, dim_cliente, dim_obligacion, dim_gestor,
        fact_cartera, fact_pagos, fact_gestiones, fact_promesas,
    )  # fmt: skip
