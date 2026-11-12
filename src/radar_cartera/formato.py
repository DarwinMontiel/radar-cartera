"""Formato colombiano (es-CO) para montos, conteos y porcentajes en textos para personas.

Se hace a mano y no con ``locale`` para no depender de los locales instalados en el sistema
(en contenedores slim y en CI suelen faltar).
"""

from __future__ import annotations

import math


def _miles(value: float, decimals: int = 0) -> str:
    texto = f"{abs(value):,.{decimals}f}"  # 1,234,567.8
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")  # 1.234.567,8


def entero(value: float | None) -> str:
    """1234567 -> '1.234.567'."""
    if value is None or not math.isfinite(value):
        return "–"
    signo = "-" if value < 0 else ""
    return f"{signo}{_miles(round(value))}"


def cop(value: float | None) -> str:
    """15106380400 -> '$ 15.106.380.400' (pesos sin decimales)."""
    if value is None or not math.isfinite(value):
        return "–"
    signo = "-" if value < 0 else ""
    return f"{signo}$ {_miles(round(value))}"


def porcentaje(value: float | None, decimals: int = 1) -> str:
    """0.0934 -> '9,3 %' (espacio antes del símbolo, como recomienda la RAE)."""
    if value is None or not math.isfinite(value):
        return "–"
    signo = "-" if value < 0 else ""
    return f"{signo}{_miles(value * 100, decimals)} %"
