from __future__ import annotations

import json

import pandas as pd

from radar_cartera.quality import QualityReport, Rule, apply_rules, validate_all
from radar_cartera.transform import clean_all
from tests.conftest import AS_OF, tiny_data


def test_apply_rules_rejects_with_first_failing_reason() -> None:
    df = pd.DataFrame({"id": ["a", "b", "c", "c"], "valor": [10, -5, None, 7]})
    report = QualityReport()
    rules = [
        Rule("duplicado", "id único", lambda d: ~d.duplicated("id")),
        Rule("valor_invalido", "valor > 0", lambda d: d["valor"] > 0),
    ]

    clean = apply_rules(df, "pagos", rules, report)

    assert clean["id"].tolist() == ["a"]
    rejected = report.rejected_frame()
    assert rejected["motivo"].tolist() == ["valor_invalido", "valor_invalido", "duplicado"]
    assert json.loads(rejected["registro"].iloc[0])["id"] == "b"
    assert [r.failed for r in report.results] == [1, 2]


def test_warn_rules_are_reported_but_keep_rows() -> None:
    df = pd.DataFrame({"canal": ["PSE", "Desconocido"]})
    report = QualityReport()
    rule = Rule("canal", "canal en catálogo", lambda d: d["canal"] == "PSE", severity="warn")

    assert len(apply_rules(df, "pagos", [rule], report)) == 2
    assert report.results[0].failed == 1
    assert report.total_rejected == 0
    # La severidad se muestra en español en el tablero, el Excel y la documentación.
    assert report.to_frame()["severidad"].tolist() == ["alerta"]


def test_validate_all_enforces_referential_integrity() -> None:
    data = tiny_data()
    data.pagos.loc[len(data.pagos)] = [
        "P9",
        "OB-NO-EXISTE",
        pd.Timestamp("2026-10-01"),
        10.0,
        "PSE",
    ]
    data.gestiones.loc[0, "id_gestor"] = "G99"

    valid, report = validate_all(data, AS_OF)

    assert "P9" not in set(valid.pagos["id_pago"])
    assert "GS1" not in set(valid.gestiones["id_gestion"])
    assert report.rejected_by_dataset() == {"gestiones": 1, "pagos": 1}


def test_future_dated_and_incomplete_promises_are_rejected() -> None:
    data = tiny_data()
    data.gestiones.loc[1, "fecha_gestion"] = pd.Timestamp("2026-11-15")
    data.gestiones.loc[2, "valor_promesa"] = float("nan")

    valid, report = validate_all(data, AS_OF)

    reasons = dict(
        zip(report.rejected_frame()["motivo"], report.rejected_frame()["conjunto"], strict=True)
    )
    assert set(reasons) == {"fecha_gestion_invalida", "promesa_incompleta"}
    assert valid.gestiones["id_gestion"].tolist() == ["GS1"]


def test_every_injected_anomaly_is_caught(synthetic) -> None:  # type: ignore[no-untyped-def]
    from radar_cartera.extract import RawData

    raw = RawData(
        synthetic.clientes.astype("string"),
        synthetic.obligaciones.astype("string"),
        synthetic.gestores.astype("string"),
        synthetic.cortes.astype("string"),
        synthetic.pagos,
        synthetic.gestiones.astype("string"),
    )
    _, report = validate_all(clean_all(raw), AS_OF)
    assert report.total_rejected == sum(synthetic.anomalies.values())
