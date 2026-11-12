"""KPIs sobre el escenario de ``tiny_data`` con valores esperados calculados a mano."""

from __future__ import annotations

import math

import pytest

from radar_cartera.domain import SALIDA
from radar_cartera.kpis import collector_ranking, compute_all, monthly_kpis, roll_rates
from radar_cartera.model import StarSchema, evaluate_promises
from tests.conftest import AS_OF, tiny_data


def _month(model: StarSchema, month: str) -> dict[str, float]:
    frame = monthly_kpis(model)
    return frame.loc[frame["anio_mes"] == month].iloc[0].to_dict()


def test_portfolio_kpis_september(tiny_model: StarSchema) -> None:
    sep = _month(tiny_model, "2026-09")
    assert sep["saldo_total"] == 6000
    assert sep["saldo_vencido"] == 5000
    assert sep["par30"] == pytest.approx(5000 / 6000)
    assert sep["par90"] == pytest.approx(0.5)
    assert sep["recaudo"] == 100
    assert math.isnan(sep["tasa_recuperacion"])  # primer corte: sin saldo vencido previo


def test_portfolio_and_collection_kpis_october(tiny_model: StarSchema) -> None:
    octubre = _month(tiny_model, "2026-10")
    assert octubre["saldo_total"] == 2500
    assert octubre["saldo_vencido"] == 1000
    assert octubre["obligaciones_mora"] == 1
    assert octubre["par30"] == 0
    assert octubre["recaudo"] == 600
    assert octubre["tasa_recuperacion"] == pytest.approx(600 / 5000)
    assert octubre["gestiones"] == 3
    assert octubre["contactabilidad"] == pytest.approx(2 / 3)
    # La promesa del 30-oct todavía no es evaluable (vence + 3 días de gracia después del corte).
    assert octubre["promesas_evaluables"] == 1
    assert octubre["efectividad_promesas"] == 1.0


def test_promise_evaluation_window_and_threshold() -> None:
    data = tiny_data()
    promesas = evaluate_promises(data.gestiones, data.pagos, AS_OF).set_index("id_gestion")
    assert promesas.loc["GS1", "valor_pagado"] == 600
    assert bool(promesas.loc["GS1", "cumplida"])
    assert not bool(promesas.loc["GS3", "evaluable"])
    assert not bool(promesas.loc["GS3", "cumplida"])


def test_promise_below_ninety_percent_is_not_fulfilled() -> None:
    data = tiny_data()
    data.pagos.loc[1, "valor"] = 530.0  # 88 % de 600
    promesas = evaluate_promises(data.gestiones, data.pagos, AS_OF).set_index("id_gestion")
    assert not bool(promesas.loc["GS1", "cumplida"])


def test_late_payment_outside_grace_does_not_count() -> None:
    data = tiny_data()
    data.pagos.loc[1, "fecha_pago"] = data.pagos.loc[1, "fecha_pago"].replace(day=18)  # 14 + 3 = 17
    promesas = evaluate_promises(data.gestiones, data.pagos, AS_OF).set_index("id_gestion")
    assert promesas.loc["GS1", "valor_pagado"] == 0


def test_roll_rates_include_exits(tiny_model: StarSchema) -> None:
    counts, rates = roll_rates(tiny_model, "2026-10")
    assert counts.loc["Al día", "1-30"] == 1
    assert counts.loc["31-60", "Al día"] == 1
    assert counts.loc["91-180", SALIDA] == 1
    assert rates.loc["Al día", "1-30"] == 1.0
    assert counts.to_numpy().sum() == 3
    for origin in ("1-30", "61-90", ">180"):
        assert rates.loc[origin].sum() == 0


def test_roll_rates_need_a_previous_cut(tiny_model: StarSchema) -> None:
    with pytest.raises(ValueError, match="corte anterior"):
        roll_rates(tiny_model, "2026-09")


def test_collector_ranking(tiny_model: StarSchema) -> None:
    ranking = collector_ranking(tiny_model, "2026-10").set_index("id_gestor")
    assert ranking.loc["G01", "ranking"] == 1
    assert ranking.loc["G01", "recaudo_promesas"] == 600
    assert ranking.loc["G01", "gestiones"] == 2
    assert ranking.loc["G01", "contactabilidad"] == 0.5
    assert ranking.loc["G02", "ranking"] == 2
    assert math.isnan(ranking.loc["G02", "efectividad_promesas"])


def test_compute_all_defaults_to_latest_month(tiny_model: StarSchema) -> None:
    bundle = compute_all(tiny_model)
    assert bundle.month == "2026-10"
    assert bundle.latest["saldo_total"] == 2500
    assert bundle.by_channel.set_index("canal_pago").loc["Oficina", "participacion"] == 1.0
    assert list(bundle.buckets.columns)[:3] == ["anio_mes", "Al día", "1-30"]
