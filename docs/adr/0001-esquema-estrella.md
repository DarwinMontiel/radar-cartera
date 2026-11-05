# ADR-0001 · Esquema estrella con snapshot mensual de cartera

- **Estado:** aceptada · **Fecha:** 2026-11

## Contexto

Negocio consulta la cartera por mes, producto, ciudad, segmento, franja de mora y gestor, y
necesita comparar cortes (¿cuánto empeoró la cartera?). Las fuentes llegan como tablas planas
por sistema (core de cartera, recaudo, CRM de cobranza).

## Decisión

Modelo dimensional (Kimball):

- Dimensiones conformadas: `dim_fecha` (con `anio_mes`, trimestre, día de la semana),
  `dim_cliente`, `dim_obligacion`, `dim_gestor`, con llaves sustitutas enteras.
- `fact_cartera` como **snapshot periódico** mensual (grano: obligación × corte).
- `fact_pagos` y `fact_gestiones` como hechos transaccionales.
- `fact_promesas` como hecho derivado con el resultado de la evaluación ya calculado.

## Consecuencias

- Power BI funciona con relaciones simples 1:* y medidas cortas (ver `powerbi/medidas.dax`).
- Las roll rates salen de comparar dos snapshots, sin reconstruir historia.
- Las dimensiones son tipo 1 (se sobrescriben). Si negocio necesita historia de atributos del
  cliente (p. ej. cambios de segmento) se migraría `dim_cliente` a SCD tipo 2.
