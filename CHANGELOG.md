# Changelog

Formato [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) · [SemVer](https://semver.org/lang/es/).

## [1.0.0] - 2026-11-05

### Agregado
- Extracción de exportes CSV y Excel sin inferencia de tipos.
- Limpieza vectorizada: documentos, nombres, ciudades, resultados de gestión, montos en formato
  colombiano y fechas mixtas.
- Motor de reglas de calidad con cuarentena, reporte auditable y 29 reglas sobre 6 datasets.
- Modelo estrella (4 dimensiones, 4 hechos) con evaluación de promesas de pago.
- Carga transaccional idempotente a PostgreSQL y 4 vistas para Power BI.
- KPIs: saldo, PAR30/PAR90, recaudo, tasa de recuperación, contactabilidad, efectividad de
  promesas, roll rates, ranking de gestores, cartera por producto y recaudo por canal.
- Reporte Excel con tablas, gráficos nativos y formato condicional; tablero HTML en GitHub Pages.
- Medidas DAX y consultas Power Query versionadas.
- Generador de datos sintéticos con anomalías registradas.
- CI con pruebas contra PostgreSQL 16 y publicación automática del tablero.

[1.0.0]: https://github.com/DarwinMontiel/radar-cartera/releases/tag/v1.0.0
