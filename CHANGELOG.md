# Changelog

Formato [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) · [SemVer](https://semver.org/lang/es/).

## [1.1.0] - 2026-11-12

### Cambiado
- El proyecto pasa a llamarse **Radar de Cartera** (`radar-cartera`, paquete `radar_cartera`).
  El tablero se publica en <https://darwinmontiel.github.io/radar-cartera/>.
- Documentación, rutas y salidas en español: `docs/arquitectura.md`, `docs/calidad-de-datos.md`,
  `docs/imagenes/`, `data/muestra/`; severidades *rechazo* / *alerta* y columna *conjunto* en el
  tablero, el Excel y `rechazados.csv`.
- La CLI muestra montos y porcentajes en formato colombiano (`$ 15.217.214.500`, `11,4 %`) y
  explica los errores en español sin *traceback*.
- Los documentos sintéticos usan un rango ficticio (prefijo 99) que no coincide con cédulas
  reales; se regeneró la muestra.

### Agregado
- Tablero: *lectura para el comité* con semáforo por variación del PAR30, botón para descargar
  los rechazados, aviso cuando no cargan los gráficos y estados vacíos.
- Chart.js con versión fija e integridad SRI.
- Pruebas de la CLI con `CliRunner`; la CLI ya entra en la medición de cobertura.
- CI en Python 3.12 y 3.13 y verificación de `--as-of` contra PostgreSQL.

### Corregido
- `--as-of` en un mes pasado mandaba a cuarentena los pagos y gestiones posteriores, dejaba los
  cortes posteriores en el modelo y calculaba los KPIs del último mes de los datos. Ahora lo
  posterior al corte pedido queda fuera de alcance y los KPIs son los del corte pedido.
- Un mismo pago podía cumplir varias promesas solapadas e inflar la efectividad y el ranking de
  gestores. Ahora cada pago se atribuye a una sola promesa (último toque).

## [1.0.0] - 2026-11-05

### Agregado
- Extracción de exportes CSV y Excel sin inferencia de tipos.
- Limpieza vectorizada: documentos, nombres, ciudades, resultados de gestión, montos en formato
  colombiano y fechas mixtas.
- Motor de reglas de calidad con cuarentena, reporte auditable y 29 reglas sobre 6 conjuntos de datos.
- Modelo estrella (4 dimensiones, 4 hechos) con evaluación de promesas de pago.
- Carga transaccional idempotente a PostgreSQL y 4 vistas para Power BI.
- KPIs: saldo, PAR30/PAR90, recaudo, tasa de recuperación, contactabilidad, efectividad de
  promesas, roll rates, ranking de gestores, cartera por producto y recaudo por canal.
- Reporte Excel con tablas, gráficos nativos y formato condicional; tablero HTML en GitHub Pages.
- Medidas DAX y consultas Power Query versionadas.
- Generador de datos sintéticos con anomalías registradas.
- CI con pruebas contra PostgreSQL 16 y publicación automática del tablero.

[1.1.0]: https://github.com/DarwinMontiel/radar-cartera/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/DarwinMontiel/radar-cartera/releases/tag/v1.0.0
