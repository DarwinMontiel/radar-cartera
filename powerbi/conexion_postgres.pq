// Power Query (M): conexión al data warehouse en PostgreSQL con parámetros.
// Crear los parámetros ServidorDW (texto, p. ej. "localhost:5432") y BaseDW ("cartera")
// en Inicio → Administrar parámetros, y una consulta por tabla con este patrón.

// ---- Consulta: dim_fecha -------------------------------------------------------------
let
    Origen = PostgreSQL.Database(ServidorDW, BaseDW),
    Tabla = Origen{[Schema = "public", Item = "dim_fecha"]}[Data],
    Tipos = Table.TransformColumnTypes(
        Tabla,
        {
            {"fecha_key", Int64.Type}, {"fecha", type date}, {"anio", Int64.Type},
            {"mes", Int64.Type}, {"anio_mes", type text}, {"nombre_mes", type text},
            {"trimestre", type text}, {"dia_semana", type text},
            {"es_fin_de_semana", type logical}, {"es_fin_de_mes", type logical}
        }
    ),
    // Ordenar meses por número y no alfabéticamente (columna de orden en el modelo).
    ConOrden = Table.AddColumn(Tipos, "orden_mes", each [anio] * 100 + [mes], Int64.Type)
in
    ConOrden

// ---- Consulta: fact_cartera ----------------------------------------------------------
let
    Origen = PostgreSQL.Database(ServidorDW, BaseDW),
    Tabla = Origen{[Schema = "public", Item = "fact_cartera"]}[Data],
    Tipos = Table.TransformColumnTypes(
        Tabla,
        {
            {"corte_key", Int64.Type}, {"obligacion_key", Int64.Type}, {"cliente_key", Int64.Type},
            {"saldo_capital", Currency.Type}, {"dias_mora", Int64.Type},
            {"bucket_mora", type text}, {"en_mora", type logical}
        }
    ),
    // Orden lógico de franjas para gráficos (Al día, 1-30, ..., >180).
    OrdenFranja = Table.AddColumn(
        Tipos,
        "orden_franja",
        each List.PositionOf({"Al día", "1-30", "31-60", "61-90", "91-180", ">180"}, [bucket_mora]),
        Int64.Type
    )
in
    OrdenFranja

// ---- Consulta: vw_kpi_mensual (para validar contra el reporte Excel) ------------------
let
    Origen = PostgreSQL.Database(ServidorDW, BaseDW, [Query = "SELECT * FROM vw_kpi_mensual"]),
    Tipos = Table.TransformColumnTypes(
        Origen,
        {
            {"saldo_total", Currency.Type}, {"saldo_vencido", Currency.Type}, {"recaudo", Currency.Type},
            {"par30", Percentage.Type}, {"par90", Percentage.Type},
            {"tasa_recuperacion", Percentage.Type}, {"contactabilidad", Percentage.Type},
            {"efectividad_promesas", Percentage.Type}
        }
    )
in
    Tipos
