# ADR-0004 · Datos sintéticos con anomalías registradas

- **Estado:** aceptada · **Fecha:** 2026-11

## Contexto

Los datos reales de cartera contienen información personal y financiera protegida (Ley 1581 de
2012 de protección de datos en Colombia). No pueden publicarse ni usarse en CI. Aun así, el
pipeline debe probarse con volúmenes y problemas de calidad realistas.

## Decisión

Un generador (`synthetic.py`) reproducible por semilla que:

- Simula la cartera mes a mes con una cadena de Markov sobre cuotas vencidas, con
  probabilidades de cura, abono y deterioro por franja, y castigo de cartera muy vencida.
- Genera gestiones coherentes con la mora (equipos temprana / tardía / recuperación), promesas y
  pagos correlacionados con esas promesas.
- Produce los exportes "como llegarían": documentos con puntos, nombres y ciudades sin
  estandarizar, montos como texto en formato colombiano, fechas mixtas en el Excel de recaudo,
  duplicados por doble exportación, referencias huérfanas y fechas futuras.
- **Registra cuántas anomalías inyectó de cada tipo**, lo que permite exigir en las pruebas que
  el pipeline las detecte todas, ni una más ni una menos.

## Consecuencias

- El repositorio es 100 % público y ejecutable por cualquiera (`make demo`).
- El tablero publicado en GitHub Pages se regenera en CI con los mismos datos.
- Los parámetros de simulación no pretenden reflejar una entidad real; reflejan dinámicas
  típicas de cartera de consumo.
