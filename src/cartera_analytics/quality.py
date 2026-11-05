"""Motor de reglas de calidad de datos.

Cada regla devuelve una máscara booleana (True = el registro cumple). Las reglas con
severidad ``reject`` envían el registro a cuarentena con el motivo; las ``warn`` solo se
reportan. El resultado es un reporte auditable de qué se revisó y qué se descartó.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

import pandas as pd

from cartera_analytics.domain import (
    CANALES_GESTION,
    CANALES_PAGO,
    EQUIPOS,
    RESULTADO_PROMESA,
    SEGMENTOS,
)
from cartera_analytics.extract import RawData

Check = Callable[[pd.DataFrame], pd.Series]
Severity = Literal["reject", "warn"]


@dataclass(frozen=True)
class Rule:
    name: str
    description: str
    check: Check
    severity: Severity = "reject"


@dataclass(frozen=True)
class RuleResult:
    dataset: str
    rule: str
    description: str
    severity: Severity
    checked: int
    failed: int

    @property
    def pass_rate(self) -> float:
        return 1.0 if self.checked == 0 else 1 - self.failed / self.checked


@dataclass
class QualityReport:
    results: list[RuleResult] = field(default_factory=list)
    rejected: list[pd.DataFrame] = field(default_factory=list)

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "dataset": r.dataset,
                    "regla": r.rule,
                    "descripcion": r.description,
                    "severidad": r.severity,
                    "revisados": r.checked,
                    "fallidos": r.failed,
                    "cumplimiento": round(r.pass_rate, 4),
                }
                for r in self.results
            ]
        )

    def rejected_frame(self) -> pd.DataFrame:
        if not self.rejected:
            return pd.DataFrame(columns=["dataset", "motivo", "registro"])
        return pd.concat(self.rejected, ignore_index=True)

    def rejected_by_dataset(self) -> dict[str, int]:
        frame = self.rejected_frame()
        counts = frame.groupby("dataset").size() if len(frame) else pd.Series(dtype="int64")
        return {str(k): int(v) for k, v in counts.items()}

    @property
    def total_rejected(self) -> int:
        return sum(len(r) for r in self.rejected)


def apply_rules(
    df: pd.DataFrame, dataset: str, rules: Iterable[Rule], report: QualityReport
) -> pd.DataFrame:
    """Aplica las reglas en orden; un registro se rechaza por la primera regla que incumple."""
    keep = pd.Series(True, index=df.index)
    reasons = pd.Series(pd.NA, index=df.index, dtype="string")
    for rule in rules:
        ok = rule.check(df).fillna(False).astype(bool)
        failed = ~ok
        report.results.append(
            RuleResult(
                dataset, rule.name, rule.description, rule.severity, len(df), int(failed.sum())
            )
        )
        if rule.severity == "reject":
            newly = failed & keep
            reasons[newly] = rule.name
            keep &= ok
    rejected = df[~keep]
    if len(rejected):
        report.rejected.append(
            pd.DataFrame(
                {
                    "dataset": dataset,
                    "motivo": reasons[~keep].to_numpy(),
                    "registro": rejected.astype("string")
                    .to_json(orient="records", lines=True, force_ascii=False)
                    .splitlines(),
                }
            )
        )
    return df[keep].reset_index(drop=True)


def _in(values: Iterable[str]) -> Callable[[pd.Series], pd.Series]:
    allowed = set(values)
    return lambda s: s.isin(allowed)


def _not_duplicated(*cols: str) -> Check:
    return lambda d: ~d.duplicated(subset=list(cols), keep="first")


def validate_all(data: RawData, as_of: date) -> tuple[RawData, QualityReport]:
    """Valida en orden de dependencia para poder verificar integridad referencial."""
    report = QualityReport()
    limit = pd.Timestamp(as_of)

    clientes = apply_rules(
        data.clientes,
        "clientes",
        [
            Rule("cliente_duplicado", "id_cliente único", _not_duplicated("id_cliente")),
            Rule("documento_invalido", "documento de 6 a 10 dígitos",
                 lambda d: d["documento"].str.fullmatch(r"\d{6,10}")),
            Rule("nombre_vacio", "nombre informado", lambda d: d["nombre"].str.len() > 2),
            Rule("ciudad_fuera_de_catalogo", "ciudad reconocida", lambda d: d["ciudad"].notna(),
                 severity="warn"),
            Rule("segmento_invalido", "segmento en catálogo", lambda d: _in(SEGMENTOS)(d["segmento"])),
        ],
        report,
    )  # fmt: skip
    clientes_ok = set(clientes["id_cliente"])

    obligaciones = apply_rules(
        data.obligaciones,
        "obligaciones",
        [
            Rule("obligacion_duplicada", "id_obligacion único", _not_duplicated("id_obligacion")),
            Rule("cliente_inexistente", "id_cliente existe en clientes",
                 lambda d: d["id_cliente"].isin(clientes_ok)),
            Rule("monto_invalido", "monto desembolsado > 0", lambda d: d["monto_desembolsado"] > 0),
            Rule("plazo_invalido", "plazo entre 1 y 120 meses",
                 lambda d: d["plazo_meses"].between(1, 120)),
            Rule("fecha_desembolso_invalida", "fecha de desembolso válida y no futura",
                 lambda d: d["fecha_desembolso"] <= limit),
        ],
        report,
    )  # fmt: skip
    obligaciones_ok = set(obligaciones["id_obligacion"])

    gestores = apply_rules(
        data.gestores,
        "gestores",
        [
            Rule("gestor_duplicado", "id_gestor único", _not_duplicated("id_gestor")),
            Rule("equipo_invalido", "equipo en catálogo", lambda d: _in(EQUIPOS)(d["equipo"])),
        ],
        report,
    )  # fmt: skip
    gestores_ok = set(gestores["id_gestor"])

    cortes = apply_rules(
        data.cortes,
        "cortes",
        [
            Rule("corte_duplicado", "una fila por obligación y corte",
                 _not_duplicated("id_obligacion", "fecha_corte")),
            Rule("obligacion_inexistente", "id_obligacion existe",
                 lambda d: d["id_obligacion"].isin(obligaciones_ok)),
            Rule("fecha_corte_invalida", "fecha de corte válida", lambda d: d["fecha_corte"].notna()),
            Rule("saldo_negativo", "saldo de capital >= 0", lambda d: d["saldo_capital"] >= 0),
            Rule("dias_mora_invalidos", "días de mora >= 0", lambda d: d["dias_mora"] >= 0),
        ],
        report,
    )  # fmt: skip

    pagos = apply_rules(
        data.pagos,
        "pagos",
        [
            Rule("pago_duplicado", "id_pago único (doble exportación)", _not_duplicated("id_pago")),
            Rule("obligacion_inexistente", "id_obligacion existe",
                 lambda d: d["id_obligacion"].isin(obligaciones_ok)),
            Rule("valor_invalido", "valor del pago > 0 (reversiones van por otro flujo)",
                 lambda d: d["valor"] > 0),
            Rule("fecha_pago_invalida", "fecha válida y no posterior al corte",
                 lambda d: d["fecha_pago"] <= limit),
            Rule("canal_desconocido", "canal de pago en catálogo",
                 lambda d: _in(CANALES_PAGO)(d["canal"]), severity="warn"),
        ],
        report,
    )  # fmt: skip

    end_of_day = limit + pd.Timedelta(days=1)
    gestiones = apply_rules(
        data.gestiones,
        "gestiones",
        [
            Rule("gestion_duplicada", "id_gestion único", _not_duplicated("id_gestion")),
            Rule("obligacion_inexistente", "id_obligacion existe",
                 lambda d: d["id_obligacion"].isin(obligaciones_ok)),
            Rule("gestor_inexistente", "id_gestor existe", lambda d: d["id_gestor"].isin(gestores_ok)),
            Rule("resultado_desconocido", "resultado en catálogo", lambda d: d["resultado"].notna()),
            Rule("fecha_gestion_invalida", "fecha válida y no posterior al corte",
                 lambda d: d["fecha_gestion"] < end_of_day),
            Rule("promesa_incompleta", "toda promesa tiene fecha y valor > 0",
                 lambda d: (d["resultado"] != RESULTADO_PROMESA)
                 | (d["fecha_promesa"].notna() & (d["valor_promesa"] > 0))),
            Rule("canal_desconocido", "canal de gestión en catálogo",
                 lambda d: _in(CANALES_GESTION)(d["canal"]), severity="warn"),
        ],
        report,
    )  # fmt: skip

    return RawData(clientes, obligaciones, gestores, cortes, pagos, gestiones), report
