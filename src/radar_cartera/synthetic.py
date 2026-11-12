"""Generador de datos sintéticos de cartera, reproducible por semilla.

Simula una cartera de consumo colombiana mes a mes con una cadena de Markov sobre las cuotas
vencidas, y produce los exportes "crudos" que entregarían los sistemas de origen, **con los
problemas de calidad típicos** (documentos con puntos, fechas en formatos mixtos, valores
como texto con separadores de miles, duplicados, referencias huérfanas) para que el pipeline
demuestre su limpieza y validación. Ningún dato corresponde a personas reales.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from radar_cartera.domain import CANALES_PAGO, RESULTADO_PROMESA

NOMBRES = [
    "Laura", "Andrés", "María", "Juan", "Valentina", "Santiago", "Camila", "Carlos", "Daniela",
    "Felipe", "Natalia", "Sebastián", "Paola", "Julián", "Sara", "Diego", "Juliana", "Mateo",
    "Carolina", "Alejandro", "Luisa", "David", "Manuela", "Jorge", "Ana", "Óscar", "Diana",
]  # fmt: skip
APELLIDOS = [
    "Gómez", "Rodríguez", "Martínez", "García", "López", "Hernández", "Pérez", "Sánchez",
    "Ramírez", "Torres", "Díaz", "Vargas", "Castro", "Rojas", "Moreno", "Jiménez", "Muñoz",
    "Ortiz", "Rincón", "Suárez", "Herrera", "Medina", "Restrepo", "Cárdenas", "Ospina",
]  # fmt: skip
CIUDADES = {
    "Bogotá": 0.35, "Medellín": 0.18, "Cali": 0.12, "Barranquilla": 0.10,
    "Bucaramanga": 0.08, "Cartagena": 0.07, "Pereira": 0.05, "Manizales": 0.05,
}  # fmt: skip
SEGMENTOS = {"Masivo": 0.7, "Preferente": 0.2, "PyME": 0.1}


@dataclass(frozen=True)
class Producto:
    peso: float
    monto: tuple[int, int]
    plazos: tuple[int, ...]
    tasa_mensual: float
    prob_impago: float  # probabilidad mensual de que una obligación al día deje de pagar


PRODUCTOS = {
    "Tarjeta de crédito": Producto(0.40, (1_000_000, 12_000_000), (24, 36, 48), 0.024, 0.055),
    "Libre inversión": Producto(0.30, (3_000_000, 40_000_000), (12, 24, 36, 48, 60), 0.016, 0.04),
    "Microcrédito": Producto(0.20, (1_000_000, 15_000_000), (6, 12, 24, 36), 0.028, 0.07),
    "Vehículo": Producto(0.10, (30_000_000, 120_000_000), (48, 60, 72), 0.011, 0.025),
}

GESTORES = [
    ("G01", "Ana Lucía Ríos", "Temprana"), ("G02", "Brayan Cortés", "Temprana"),
    ("G03", "Claudia Peña", "Temprana"), ("G04", "Esteban Mora", "Temprana"),
    ("G05", "Fernanda Gil", "Temprana"), ("G06", "Hernán Quintero", "Tardía"),
    ("G07", "Isabel Acosta", "Tardía"), ("G08", "Jhon Ramírez", "Tardía"),
    ("G09", "Karen Salazar", "Tardía"), ("G10", "Leonardo Prieto", "Recuperación"),
    ("G11", "Mónica Arango", "Recuperación"), ("G12", "Nelson Vega", "Recuperación"),
]  # fmt: skip

MAX_CUOTAS_VENCIDAS = 8

# Rangos [inicio, fin) de documentos ficticios: 9.900.000.000-9.999.999.999 y 990.000.000-999.999.999.
DOC_FICTICIO_10 = (9_900_000_000, 10_000_000_000)
DOC_FICTICIO_9 = (990_000_000, 1_000_000_000)


@dataclass(frozen=True)
class _Obligacion:
    id_obligacion: str
    producto: Producto
    monto_desembolsado: float
    plazo_meses: int
    tasa_mensual: float
    fecha_desembolso: date


@dataclass(frozen=True)
class SyntheticConfig:
    seed: int = 42
    clients: int = 1500
    months: int = 12
    last_cut: date = date(2026, 10, 31)
    anomalies: bool = True


@dataclass
class SyntheticData:
    clientes: pd.DataFrame
    obligaciones: pd.DataFrame
    gestores: pd.DataFrame
    cortes: pd.DataFrame
    pagos: pd.DataFrame
    gestiones: pd.DataFrame
    anomalies: dict[str, int] = field(default_factory=dict)


def month_ends(last_cut: date, months: int) -> list[date]:
    return [d.date() for d in pd.date_range(end=last_cut, periods=months, freq="ME")]


def _cuota(monto: float, tasa: float, plazo: int) -> float:
    return monto * tasa / (1 - (1 + tasa) ** -plazo)


def _amortizar(saldo: float, tasa: float, cuota: float, cuotas: int) -> float:
    for _ in range(cuotas):
        saldo = saldo * (1 + tasa) - cuota
    return max(round(saldo, -2), 0.0)


def _weighted(rng: np.random.Generator, options: dict[str, float], size: int) -> np.ndarray:
    keys = list(options)
    probs = np.array(list(options.values()))
    return rng.choice(keys, size=size, p=probs / probs.sum())


def _random_datetime(rng: np.random.Generator, start: date, end: date) -> datetime:
    days = (end - start).days
    day = start + timedelta(days=int(rng.integers(0, days + 1)))
    return datetime.combine(day, time(int(rng.integers(8, 19)), int(rng.integers(0, 60))))


class _Simulator:
    def __init__(self, cfg: SyntheticConfig) -> None:
        self.cfg = cfg
        self.rng = np.random.default_rng(cfg.seed)
        # Se simula un mes extra al inicio para que el primer corte reportado tenga la
        # actividad (pagos, gestiones) del mes que lo antecede.
        self.cuts = month_ends(cfg.last_cut, cfg.months + 1)
        self.first_reported = self.cuts[1]
        self.gestores_por_equipo: dict[str, list[str]] = {}
        for gid, _, equipo in GESTORES:
            self.gestores_por_equipo.setdefault(equipo, []).append(gid)
        self.cortes: list[tuple[Any, ...]] = []
        self.pagos: list[tuple[Any, ...]] = []
        self.gestiones: list[tuple[Any, ...]] = []

    # ------------------------------------------------------------------ maestros
    def clientes(self) -> pd.DataFrame:
        rng, n = self.rng, self.cfg.clients
        # Documentos en un rango ficticio a propósito (prefijo 99, 9 o 10 dígitos): pasan la
        # regla de formato, pero quedan lejos de la numeración habitual de cédulas colombianas,
        # para no asociar nombres ficticios a documentos de personas reales (ADR-0004).
        diez = rng.integers(DOC_FICTICIO_10[0], DOC_FICTICIO_10[1], size=n * 2)
        nueve = rng.integers(DOC_FICTICIO_9[0], DOC_FICTICIO_9[1], size=n * 2)
        docs = np.where(rng.random(n * 2) < 0.75, diez, nueve)
        docs = pd.unique(docs)[:n]
        nombres = [
            f"{rng.choice(NOMBRES)} {rng.choice(APELLIDOS)} {rng.choice(APELLIDOS)}"
            for _ in range(n)
        ]
        vinculacion = pd.to_datetime("2015-01-01") + pd.to_timedelta(
            rng.integers(0, 4200, size=n), unit="D"
        )
        return pd.DataFrame(
            {
                "id_cliente": [f"CL-{i:06d}" for i in range(1, n + 1)],
                "documento": docs.astype(str),
                "nombre": nombres,
                "ciudad": _weighted(rng, CIUDADES, n),
                "segmento": _weighted(rng, SEGMENTOS, n),
                "fecha_vinculacion": vinculacion.date,
            }
        )

    def obligaciones(self, clientes: pd.DataFrame) -> pd.DataFrame:
        rng = self.rng
        owners = np.repeat(
            clientes["id_cliente"].to_numpy(), np.where(rng.random(len(clientes)) < 0.2, 2, 1)
        )
        n = len(owners)
        productos = _weighted(rng, {k: v.peso for k, v in PRODUCTOS.items()}, n)
        first_cut = self.cuts[1]
        latest = self.cuts[-2]
        span = (latest - date(2022, 1, 1)).days
        rows = []
        for i, (owner, prod) in enumerate(zip(owners, productos, strict=True), start=1):
            p = PRODUCTOS[prod]
            monto = round(float(rng.uniform(*p.monto)), -4)
            plazo = int(rng.choice(p.plazos))
            desembolso = date(2022, 1, 1) + timedelta(days=int(rng.integers(0, span)))
            # Obligaciones ya vencidas por plazo antes del primer corte no hacen parte de la cartera.
            if (first_cut - desembolso).days / 30 > plazo:
                desembolso = first_cut - timedelta(days=int(rng.integers(30, 300)))
            rows.append((f"OB-{i:07d}", owner, prod, monto, plazo, p.tasa_mensual, desembolso))
        return pd.DataFrame(
            rows,
            columns=[
                "id_obligacion", "id_cliente", "producto", "monto_desembolsado",
                "plazo_meses", "tasa_mensual", "fecha_desembolso",
            ],
        )  # fmt: skip

    # ------------------------------------------------------------------ dinámica mensual
    def simulate(self, obligaciones: pd.DataFrame) -> None:
        rows = zip(
            obligaciones["id_obligacion"].tolist(),
            obligaciones["producto"].tolist(),
            obligaciones["monto_desembolsado"].tolist(),
            obligaciones["plazo_meses"].tolist(),
            obligaciones["tasa_mensual"].tolist(),
            obligaciones["fecha_desembolso"].tolist(),
            strict=True,
        )
        for id_ob, producto, monto, plazo, tasa, desembolso in rows:
            ob = _Obligacion(
                str(id_ob), PRODUCTOS[producto], float(monto), int(plazo), float(tasa), desembolso
            )
            self._simulate_one(ob)

    def _simulate_one(self, ob: _Obligacion) -> None:
        rng = self.rng
        prod = ob.producto
        cuota = _cuota(ob.monto_desembolsado, ob.tasa_mensual, ob.plazo_meses)
        active_cuts = [c for c in self.cuts if c > ob.fecha_desembolso + timedelta(days=25)]
        if active_cuts:
            pagadas = max(0, (active_cuts[0] - ob.fecha_desembolso).days // 30)
            saldo = _amortizar(ob.monto_desembolsado, ob.tasa_mensual, cuota, pagadas)
            k = int(rng.choice([0, 1, 2, 3, 4, 5], p=[0.84, 0.07, 0.04, 0.02, 0.02, 0.01]))

            for idx, cut in enumerate(active_cuts):
                if saldo <= 0:
                    break
                dias = 0 if k == 0 else k * 30 - int(rng.integers(0, 30))
                if cut >= self.first_reported:
                    self.cortes.append((ob.id_obligacion, cut, saldo, dias))
                if idx + 1 == len(active_cuts):
                    break
                nxt = active_cuts[idx + 1]
                month_start = cut + timedelta(days=1)

                if k == 0:
                    if rng.random() < prod.prob_impago:
                        k = 1
                    else:
                        saldo = _amortizar(saldo, ob.tasa_mensual, cuota, 1)
                    continue

                # Obligación en mora: se gestiona y puede normalizarse, abonar o rodar.
                u = rng.random()
                p_cure = {1: 0.38, 2: 0.24, 3: 0.15}.get(k, 0.07)
                p_partial = 0.22 if k < 6 else 0.08
                pago = 0.0
                if u < p_cure:
                    pago = round(cuota * k * (1 + 0.02 * k), -2)
                    saldo = _amortizar(saldo, ob.tasa_mensual, cuota, k)
                    k_next = 0
                elif u < p_cure + p_partial:
                    pago = round(cuota, -2)
                    saldo = _amortizar(saldo, ob.tasa_mensual, cuota, 1)
                    k_next = k
                else:
                    k_next = min(k + 1, MAX_CUOTAS_VENCIDAS)

                promesas = self._gestionar(ob.id_obligacion, k, cuota, pago, month_start, nxt)
                if pago > 0:
                    if promesas:
                        target = promesas[-1] + timedelta(days=int(rng.integers(-2, 4)))
                        fecha_pago = min(max(target, month_start), nxt)
                    else:
                        fecha_pago = month_start + timedelta(
                            days=int(rng.integers(0, (nxt - month_start).days + 1))
                        )
                    canal = str(rng.choice(CANALES_PAGO, p=[0.45, 0.3, 0.15, 0.1]))
                    self.pagos.append((ob.id_obligacion, fecha_pago, pago, canal))

                # Castigo: obligaciones con mora muy alta salen de cartera.
                if k_next == MAX_CUOTAS_VENCIDAS and rng.random() < 0.3:
                    break
                k = k_next

    def _gestionar(
        self, id_obligacion: str, k: int, cuota: float, pago: float, start: date, end: date
    ) -> list[date]:
        rng = self.rng
        equipo = "Temprana" if k == 1 else "Tardía" if k <= 3 else "Recuperación"
        n = int(min(max(rng.poisson(1.2 + 0.5 * k), 1), 8))
        p_contacto = max(0.18, 0.58 - 0.05 * k)
        p_promesa = 0.7 if pago > 0 else 0.25
        promesas: list[date] = []
        registros = []
        for _ in range(n):
            gestor = str(rng.choice(self.gestores_por_equipo[equipo]))
            canal = str(rng.choice(["Llamada", "WhatsApp", "Visita"], p=[0.62, 0.3, 0.08]))
            cuando = _random_datetime(rng, start, end - timedelta(days=2))
            contacto = rng.random() < (p_contacto + (0.2 if canal == "Visita" else 0.0))
            fecha_promesa: date | None = None
            valor_promesa: float | None = None
            if contacto and rng.random() < p_promesa:
                resultado = RESULTADO_PROMESA
                fecha_promesa = cuando.date() + timedelta(days=int(rng.integers(1, 9)))
                base = pago if pago > 0 else cuota * int(rng.integers(1, k + 1))
                valor_promesa = round(base * float(rng.uniform(0.92, 1.1)), -2)
                promesas.append(fecha_promesa)
            elif contacto:
                resultado = str(
                    rng.choice(
                        ["Contacto titular", "Contacto tercero", "Rehúsa pago"], p=[0.45, 0.35, 0.2]
                    )
                )
            else:
                resultado = str(
                    rng.choice(
                        ["No contesta", "Buzón de voz", "Número errado"], p=[0.6, 0.27, 0.13]
                    )
                )
            registros.append(
                (id_obligacion, gestor, cuando, canal, resultado, fecha_promesa, valor_promesa)
            )
        registros.sort(key=lambda r: r[2])
        self.gestiones.extend(registros)
        promesas.sort()
        return promesas

    def frames(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        cortes = pd.DataFrame(
            self.cortes, columns=["id_obligacion", "fecha_corte", "saldo_capital", "dias_mora"]
        )
        pagos = pd.DataFrame(self.pagos, columns=["id_obligacion", "fecha_pago", "valor", "canal"])
        pagos = pagos.sort_values("fecha_pago", kind="stable").reset_index(drop=True)
        pagos.insert(0, "id_pago", [f"PG-{i:07d}" for i in range(1, len(pagos) + 1)])
        gestiones = pd.DataFrame(
            self.gestiones,
            columns=[
                "id_obligacion", "id_gestor", "fecha_gestion", "canal", "resultado",
                "fecha_promesa", "valor_promesa",
            ],
        )  # fmt: skip
        gestiones = gestiones.sort_values("fecha_gestion", kind="stable").reset_index(drop=True)
        gestiones.insert(0, "id_gestion", [f"GS-{i:07d}" for i in range(1, len(gestiones) + 1)])
        return cortes, pagos, gestiones


def generate(cfg: SyntheticConfig = SyntheticConfig()) -> SyntheticData:
    sim = _Simulator(cfg)
    clientes = sim.clientes()
    obligaciones = sim.obligaciones(clientes)
    sim.simulate(obligaciones)
    cortes, pagos, gestiones = sim.frames()
    gestores = pd.DataFrame(GESTORES, columns=["id_gestor", "nombre", "equipo"])
    return SyntheticData(clientes, obligaciones, gestores, cortes, pagos, gestiones)


# ---------------------------------------------------------------------- exportes "sucios"
def _sample(rng: np.random.Generator, n: int, rate: float) -> np.ndarray:
    k = max(1, round(n * rate)) if n else 0
    return rng.choice(n, size=k, replace=False) if k else np.array([], dtype=int)


def _cop(value: float) -> str:
    return "$ " + f"{value:,.0f}".replace(",", ".")


def _messy_case(rng: np.random.Generator, text: str) -> str:
    style = rng.integers(0, 3)
    text = text.upper() if style == 0 else text.lower() if style == 1 else text
    return "  " + text.replace(" ", "   ", 1) + " "


def dirty_exports(data: SyntheticData, seed: int) -> SyntheticData:
    """Inyecta problemas de calidad realistas y registra cuántos de cada tipo se inyectaron."""
    rng = np.random.default_rng(seed + 1)
    log: dict[str, int] = {}

    clientes = data.clientes.copy()
    idx = _sample(rng, len(clientes), 0.04)
    clientes.loc[idx, "documento"] = [
        f"{int(d):,}".replace(",", ".") for d in clientes.loc[idx, "documento"]
    ]
    idx = _sample(rng, len(clientes), 0.08)
    clientes.loc[idx, "nombre"] = [_messy_case(rng, n) for n in clientes.loc[idx, "nombre"]]
    idx = _sample(rng, len(clientes), 0.06)
    clientes.loc[idx, "ciudad"] = (
        clientes.loc[idx, "ciudad"].str.lower().str.normalize("NFKD")
        .str.encode("ascii", "ignore").str.decode("ascii")
    )  # fmt: skip
    dup = clientes.iloc[_sample(rng, len(clientes), 0.005)]
    log["clientes_duplicados"] = len(dup)
    clientes = pd.concat([clientes, dup], ignore_index=True)

    cortes = data.cortes.copy()
    idx = _sample(rng, len(cortes), 0.002)
    cortes.loc[idx, "saldo_capital"] = -cortes.loc[idx, "saldo_capital"]
    log["cortes_saldo_negativo"] = len(idx)

    pagos = data.pagos.copy().astype({"valor": object, "fecha_pago": object})
    n = len(pagos)
    neg = _sample(rng, n, 0.003)
    pagos.loc[neg, "valor"] = [-float(v) for v in pagos.loc[neg, "valor"]]
    log["pagos_valor_negativo"] = len(neg)
    orphan = np.setdiff1d(_sample(rng, n, 0.003), neg)
    pagos.loc[orphan, "id_obligacion"] = [f"OB-9{int(i):06d}" for i in orphan]
    log["pagos_huerfanos"] = len(orphan)
    as_text = np.setdiff1d(_sample(rng, n, 0.3), neg)
    pagos.loc[as_text, "valor"] = [_cop(float(v)) for v in pagos.loc[as_text, "valor"]]
    dmy = _sample(rng, n, 0.2)
    pagos.loc[dmy, "fecha_pago"] = [d.strftime("%d/%m/%Y") for d in pagos.loc[dmy, "fecha_pago"]]
    dup = pagos.iloc[np.setdiff1d(_sample(rng, n, 0.006), np.union1d(neg, orphan))]
    log["pagos_duplicados"] = len(dup)
    pagos = pd.concat([pagos, dup], ignore_index=True)

    gestiones = data.gestiones.copy()
    n = len(gestiones)
    orphan = _sample(rng, n, 0.004)
    gestiones.loc[orphan, "id_obligacion"] = [f"OB-8{int(i):06d}" for i in orphan]
    log["gestiones_huerfanas"] = len(orphan)
    noisy = np.setdiff1d(_sample(rng, n, 0.03), orphan)
    gestiones.loc[noisy, "resultado"] = [
        f" {r.lower()} " if i % 2 else r.upper()
        for i, r in enumerate(gestiones.loc[noisy, "resultado"])
    ]
    future = np.setdiff1d(_sample(rng, n, 0.002), np.union1d(orphan, noisy))
    gestiones.loc[future, "fecha_gestion"] = [
        d.replace(year=d.year + 1) for d in gestiones.loc[future, "fecha_gestion"]
    ]
    log["gestiones_fecha_futura"] = len(future)

    return SyntheticData(
        clientes, data.obligaciones, data.gestores, cortes, pagos, gestiones, anomalies=log
    )


def write_raw(data: SyntheticData, out_dir: Path) -> list[Path]:
    """Escribe los exportes tal como los entregarían los sistemas de origen."""
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "cartera").mkdir(exist_ok=True)
    written = []
    for name in ("clientes", "obligaciones", "gestores", "gestiones"):
        path = out_dir / f"{name}.csv"
        getattr(data, name).to_csv(path, index=False, encoding="utf-8")
        written.append(path)
    for cut, frame in data.cortes.groupby("fecha_corte", sort=True):
        path = out_dir / "cartera" / f"corte_{pd.Timestamp(str(cut)):%Y-%m}.csv"
        frame.to_csv(path, index=False, encoding="utf-8")
        written.append(path)
    path = out_dir / "pagos.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        data.pagos.to_excel(writer, sheet_name="Recaudo", index=False)
    written.append(path)
    return written
