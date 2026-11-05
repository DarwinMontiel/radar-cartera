# ADR-0003 · Una sola definición por KPI, verificada en pandas y SQL

- **Estado:** aceptada · **Fecha:** 2026-11

## Contexto

El problema más común en BI no es técnico: es que el PAR30 del Excel de operaciones no coincide
con el del tablero de gerencia. Aquí los KPIs se consumen por tres vías: el reporte Excel y el
tablero HTML (calculados en pandas), y Power BI (sobre vistas SQL y medidas DAX).

## Decisión

1. Cada KPI se define una vez en `docs/kpis.md` (fórmula, granularidad y reglas de borde).
2. Se implementa en pandas (`kpis.py`), en SQL estándar (`sql/views.sql`) y en DAX
   (`powerbi/medidas.dax`).
3. Las vistas usan solo SQL estándar (CTEs y funciones de ventana) para correr igual en SQLite y
   PostgreSQL. Así **las pruebas comparan pandas contra SQL** en cada commit (SQLite) y en CI
   contra PostgreSQL real.

## Consecuencias

- Si alguien cambia una fórmula en un solo lugar, la prueba falla.
- Las vistas no usan funciones propias de PostgreSQL (`FILTER`, `DATE_TRUNC`); las consultas
  ad hoc que sí las usan viven aparte en `sql/consultas_analiticas.sql`, también probadas en CI.
- DAX no se puede probar automáticamente fuera de Power BI: se valida manualmente contra
  `vw_kpi_mensual` (procedimiento en `powerbi/README.md`).
