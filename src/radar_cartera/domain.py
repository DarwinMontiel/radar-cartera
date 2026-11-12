"""Catálogos y reglas de negocio de cobranzas compartidos por todo el pipeline."""

from __future__ import annotations

from typing import Final

# Franjas de mora (aging). El orden importa: se usa como categoría ordenada.
BUCKETS: Final[list[str]] = ["Al día", "1-30", "31-60", "61-90", "91-180", ">180"]
BUCKET_EDGES: Final[list[float]] = [-1, 0, 30, 60, 90, 180, float("inf")]
SALIDA: Final[str] = "Salida de cartera"  # destino en roll rates: cancelada o castigada

CANALES_GESTION: Final[list[str]] = ["Llamada", "WhatsApp", "Visita"]
CANALES_PAGO: Final[list[str]] = ["PSE", "Corresponsal bancario", "Oficina", "Débito automático"]
SEGMENTOS: Final[list[str]] = ["Masivo", "Preferente", "PyME"]
EQUIPOS: Final[list[str]] = ["Temprana", "Tardía", "Recuperación"]

RESULTADO_PROMESA: Final[str] = "Promesa de pago"
RESULTADOS_CONTACTO: Final[frozenset[str]] = frozenset(
    {"Contacto titular", "Contacto tercero", "Rehúsa pago", RESULTADO_PROMESA}
)
RESULTADOS_SIN_CONTACTO: Final[frozenset[str]] = frozenset(
    {"No contesta", "Buzón de voz", "Número errado"}
)
RESULTADOS: Final[frozenset[str]] = RESULTADOS_CONTACTO | RESULTADOS_SIN_CONTACTO

CIUDADES: Final[dict[str, str]] = {
    "bogota": "Bogotá",
    "bogota d.c.": "Bogotá",
    "medellin": "Medellín",
    "cali": "Cali",
    "barranquilla": "Barranquilla",
    "bucaramanga": "Bucaramanga",
    "cartagena": "Cartagena",
    "pereira": "Pereira",
    "manizales": "Manizales",
}

# Promesa cumplida: pagos >= 90 % de lo prometido entre la gestión y 3 días después de la
# fecha pactada. Solo se evalúan promesas cuyo plazo (fecha + gracia) ya venció al corte.
PROMESA_DIAS_GRACIA: Final[int] = 3
PROMESA_PORCENTAJE_MINIMO: Final[float] = 0.9

MESES: Final[list[str]] = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]  # fmt: skip
DIAS: Final[list[str]] = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
