from __future__ import annotations

import pytest

from radar_cartera.formato import cop, entero, porcentaje


@pytest.mark.parametrize(
    ("value", "expected"),
    [(15_106_380_400, "$ 15.106.380.400"), (81_443_600.4, "$ 81.443.600"), (0, "$ 0"),
     (-1500, "-$ 1.500"), (None, "–"), (float("nan"), "–")],
)  # fmt: skip
def test_cop(value: float | None, expected: str) -> None:
    assert cop(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.0934, "9,3 %"), (1, "100,0 %"), (0.12345, "12,3 %"), (-0.004, "-0,4 %"), (None, "–")],
)
def test_porcentaje(value: float | None, expected: str) -> None:
    assert porcentaje(value) == expected


def test_entero_y_decimales() -> None:
    assert entero(1712) == "1.712"
    assert entero(float("inf")) == "–"
    assert porcentaje(0.123456, decimals=2) == "12,35 %"
