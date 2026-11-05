# ADR-0002 · Carga *full refresh* transaccional e idempotente

- **Estado:** aceptada · **Fecha:** 2026-11

## Contexto

El pipeline corre a diario sobre los exportes completos de los sistemas de origen. Si una
ejecución falla a mitad de la carga, los reportes de Power BI no pueden quedar con datos
mezclados de dos días. Si se re-ejecuta, no puede duplicar filas.

## Opciones

| Opción | A favor | En contra |
|---|---|---|
| Incremental por corte (`DELETE` del corte + `INSERT`) | Escala a millones de filas | Requiere llaves sustitutas estables entre corridas (dimensiones persistentes) |
| *Upsert* fila a fila | Mínimo volumen escrito | Lento con `to_sql`; lógica de conflictos por tabla |
| **Full refresh en una transacción** | Simple, idempotente, atómico | Reescribe todo en cada corrida |

## Decisión

*Full refresh* dentro de **una sola transacción**: eliminar vistas → crear tablas si no
existen → `DELETE` de hechos y dimensiones → insertar en orden de dependencia → recrear vistas.
PostgreSQL tiene DDL transaccional, así que un error deja la base exactamente como estaba.

## Consecuencias

- Re-ejecutar el pipeline es siempre seguro (probado en `test_load_is_idempotent` y en la prueba
  de integración con PostgreSQL).
- El volumen actual (decenas de miles de filas) se carga en ~1,5 s.
- **Umbral de revisión:** si la carga supera ~5 minutos o el DW pasa de unos pocos millones de
  filas, migrar a carga incremental por corte con `COPY` y dimensiones con llaves persistentes.
