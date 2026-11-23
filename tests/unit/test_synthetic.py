from __future__ import annotations

from datetime import date

import pandas as pd

from radar_cartera.synthetic import SyntheticConfig, dirty_exports, generate, month_ends


def test_generation_is_deterministic() -> None:
    a = generate(SyntheticConfig(seed=3, clients=80, months=3))
    b = generate(SyntheticConfig(seed=3, clients=80, months=3))
    pd.testing.assert_frame_equal(a.gestiones, b.gestiones)
    pd.testing.assert_frame_equal(a.cortes, b.cortes)


def test_reported_cuts_match_configuration() -> None:
    cfg = SyntheticConfig(seed=1, clients=60, months=5)
    data = generate(cfg)
    assert sorted(data.cortes["fecha_corte"].unique()) == month_ends(cfg.last_cut, 5)


def test_clean_data_is_referentially_consistent() -> None:
    data = generate(SyntheticConfig(seed=5, clients=120, months=4))
    obligaciones = set(data.obligaciones["id_obligacion"])
    assert set(data.cortes["id_obligacion"]) <= obligaciones
    assert set(data.pagos["id_obligacion"]) <= obligaciones
    assert set(data.gestiones["id_gestor"]) <= set(data.gestores["id_gestor"])
    assert data.clientes["documento"].is_unique
    assert (data.pagos["valor"] > 0).all()


def test_documents_are_in_a_fictitious_range() -> None:
    """Los documentos sintéticos no deben caer en la numeración de cédulas reales."""
    docs = generate(SyntheticConfig(seed=11, clients=500, months=3)).clientes["documento"]
    assert docs.str.fullmatch(r"99\d{7,8}").all()


def test_dirty_exports_inject_logged_anomalies(synthetic) -> None:  # type: ignore[no-untyped-def]
    assert sum(synthetic.anomalies.values()) > 0
    as_text = synthetic.pagos["valor"].map(lambda v: isinstance(v, str))
    assert as_text.any()
    assert synthetic.pagos["id_pago"].duplicated().sum() == synthetic.anomalies["pagos_duplicados"]


def test_future_dated_activity_survives_february_29() -> None:
    """Una gestión del 29-feb se corre un año sin fallar (2029 no es bisiesto)."""
    data = generate(SyntheticConfig(seed=3, clients=60, months=3, last_cut=date(2028, 4, 30)))
    data.gestiones["fecha_gestion"] = pd.Timestamp("2028-02-29 10:00")
    dirty = dirty_exports(data, seed=3)
    assert dirty.anomalies["gestiones_fecha_futura"] > 0
    assert (dirty.gestiones["fecha_gestion"] == pd.Timestamp("2029-02-28 10:00")).any()
