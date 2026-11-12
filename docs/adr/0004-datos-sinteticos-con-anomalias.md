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
- Genera los documentos de identidad en un **rango ficticio** (prefijo `99`, de 9 o 10 dígitos:
  990.000.000-999.999.999 y 9.900.000.000-9.999.999.999). Siguen pasando la regla de formato
  (6 a 10 dígitos), pero quedan fuera de la numeración de cédulas colombianas. Así ningún
  nombre de la muestra pública puede quedar asociado al documento de una persona real dentro de
  un archivo de cartera en mora. Una prueba (`test_documents_are_in_a_fictitious_range`) lo
  garantiza.

## Consecuencias

- El repositorio es 100 % público y ejecutable por cualquiera (`make demo`).
- El tablero publicado en GitHub Pages se regenera en CI con los mismos datos.
- Los parámetros de simulación no pretenden reflejar una entidad real; reflejan dinámicas
  típicas de cartera de consumo.
