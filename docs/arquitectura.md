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
| Orquestación | `pipeline.py`, `cli.py` | Alcance por fecha de corte, pasos cronometrados, manifiesto de ejecución, CLI. |
| Formato | `formato.py` | Montos y porcentajes en formato colombiano (`$ 1.234.567`, `9,3 %`) sin depender de `locale`. |

## Una ejecución, paso a paso

```mermaid
sequenceDiagram
    autonumber
    actor A as Analista de cartera
    participant CLI as cartera run
    participant P as pipeline.py
    participant Q as quality.py
    participant DW as PostgreSQL
    participant R as Reportes

    A->>CLI: --raw data/raw --as-of 2026-10-31
    CLI->>P: run_pipeline()
    P->>P: extraer (todo como texto) y limpiar
    P->>P: recortar al corte (lo posterior queda fuera de alcance)
    P->>Q: validate_all(datos, corte)
    Q-->>P: válidos + reporte de calidad + cuarentena
    P->>P: modelo estrella y evaluación de promesas
    opt con --db o CARTERA_DATABASE_URL
        P->>DW: full refresh en una transacción + vistas
        DW-->>P: filas cargadas por tabla
    end
    P->>P: KPIs del último corte válido
    P->>R: Excel, tablero HTML, rechazados.csv, kpi_mensual.csv
    P->>R: manifest.json (filas por etapa, tiempos, rechazos)
    CLI-->>A: resumen con $ 15.217.214.500 · PAR30 11,4 %
```

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
  ventana (cada pago se atribuye a una sola promesa, por *último toque*; ver
  [kpis.md](kpis.md#un-pago-una-sola-promesa-atribución-por-último-toque)) y precalcula
  `valor_pagado`, `evaluable` y `cumplida`, para que Power BI no tenga que hacer ese cruce
  costoso en DAX.
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
