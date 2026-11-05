# Arquitectura

## Flujo de datos

```mermaid
flowchart LR
    subgraph Origen["Sistemas de origen (exportes)"]
        A1[clientes.csv]
        A2[obligaciones.csv]
        A3[cartera/corte_AAAA-MM.csv]
        A4[pagos.xlsx]
        A5[gestiones.csv]
    end
    subgraph Pipeline["cartera run"]
        E[Extracción<br/>todo como texto] --> L[Limpieza<br/>estandarización]
        L --> V{Validación<br/>reglas de calidad}
        V -- válidos --> M[Modelo estrella<br/>+ evaluación de promesas]
        V -- rechazados --> Q[(rechazados.csv)]
        M --> K[KPIs pandas]
    end
    Origen --> E
    M -- full refresh transaccional --> DW[(PostgreSQL<br/>dims · facts · vistas)]
    DW --> PBI[Power BI<br/>medidas DAX]
    K --> X[Reporte Excel]
    K --> H[Tablero HTML<br/>GitHub Pages]
    K --> J[manifest.json]
```

| Etapa | Módulo | Responsabilidad |
|---|---|---|
| Extracción | `extract.py` | Lee CSV y Excel sin inferir tipos (un documento `0012345` no se convierte en número). |
| Limpieza | `transform.py` | Funciones puras y vectorizadas de estandarización. |
| Validación | `quality.py` | Motor de reglas declarativo con cuarentena y reporte auditable. |
| Modelado | `model.py` | Llaves sustitutas, dimensión fecha, hechos y evaluación de promesas. |
| Carga | `warehouse.py` | DDL con SQLAlchemy, carga transaccional idempotente y vistas SQL. |
| KPIs | `kpis.py` | Indicadores mensuales, franjas, roll rates, ranking, producto, canal. |
| Reportes | `report_excel.py`, `report_html.py` | Excel con tablas, gráficos y formato condicional; tablero HTML. |
| Orquestación | `pipeline.py`, `cli.py` | Pasos cronometrados, manifiesto de ejecución, CLI. |

## Modelo dimensional

```mermaid
erDiagram
    dim_fecha ||--o{ fact_cartera : corte_key
    dim_fecha ||--o{ fact_pagos : fecha_key
    dim_fecha ||--o{ fact_gestiones : fecha_key
    dim_fecha ||--o{ fact_promesas : "fecha_promesa_key / fecha_gestion_key"
    dim_cliente ||--o{ dim_obligacion : cliente_key
    dim_obligacion ||--o{ fact_cartera : obligacion_key
    dim_obligacion ||--o{ fact_pagos : obligacion_key
    dim_obligacion ||--o{ fact_gestiones : obligacion_key
    dim_gestor ||--o{ fact_gestiones : gestor_key
    dim_gestor ||--o{ fact_promesas : gestor_key

    fact_cartera {
        int corte_key PK
        int obligacion_key PK
        numeric saldo_capital
        int dias_mora
        varchar bucket_mora
        bool en_mora
    }
    fact_pagos {
        varchar id_pago PK
        int fecha_key
        numeric valor
        varchar canal_pago
    }
    fact_gestiones {
        varchar id_gestion PK
        int fecha_key
        varchar canal
        varchar resultado
        bool es_contacto
        bool es_promesa
    }
    fact_promesas {
        varchar id_gestion PK
        int fecha_gestion_key
        int fecha_promesa_key
        numeric valor_prometido
        numeric valor_pagado
        bool evaluable
        bool cumplida
    }
```

- `fact_cartera` es un **snapshot periódico** (una fila por obligación y corte): permite
  comparar cortes y calcular roll rates.
- `fact_pagos` y `fact_gestiones` son hechos **transaccionales**.
- `fact_promesas` es un hecho **derivado**: el pipeline cruza cada promesa con los pagos de su
  ventana y precalcula `valor_pagado`, `evaluable` y `cumplida`, para que Power BI no tenga
  que hacer ese cruce costoso en DAX.
- El DDL completo para PostgreSQL se obtiene con `cartera ddl --dialect postgresql`.

## Decisiones

| ADR | Decisión |
|---|---|
| [0001](adr/0001-esquema-estrella.md) | Esquema estrella con snapshot mensual en lugar de tablas planas |
| [0002](adr/0002-carga-full-refresh-transaccional.md) | Carga *full refresh* transaccional e idempotente |
| [0003](adr/0003-una-definicion-por-kpi.md) | Una sola definición por KPI, verificada en pandas y SQL |
| [0004](adr/0004-datos-sinteticos-con-anomalias.md) | Datos sintéticos con anomalías registradas para probar la calidad |

## Rendimiento

Con la configuración por defecto (1.500 clientes, 12 cortes, ~30 mil filas en el DW) el pipeline
completo corre en ~3 s, de los cuales ~1,5 s son la carga a la base. Para volúmenes de millones
de filas el siguiente paso es reemplazar `DataFrame.to_sql` por `COPY` de PostgreSQL y hacer la
carga incremental por corte (ver ADR-0002).
