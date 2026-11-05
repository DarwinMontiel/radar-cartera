-- Vistas de consumo para Power BI / Excel / analistas.
-- SQL estándar (CTEs + funciones de ventana): corre igual en PostgreSQL y en SQLite,
-- lo que permite validarlas en pruebas unitarias y en CI contra PostgreSQL.
-- Definiciones de negocio: docs/kpis.md

-- 1. KPIs mensuales de cartera y cobranza --------------------------------------------
CREATE VIEW vw_kpi_mensual AS
WITH cartera AS (
    SELECT f.anio_mes,
           COUNT(*)                                                            AS obligaciones,
           SUM(c.saldo_capital)                                                AS saldo_total,
           SUM(CASE WHEN c.dias_mora > 0  THEN c.saldo_capital ELSE 0 END)     AS saldo_vencido,
           SUM(CASE WHEN c.dias_mora > 0  THEN 1 ELSE 0 END)                   AS obligaciones_mora,
           SUM(CASE WHEN c.dias_mora > 30 THEN c.saldo_capital ELSE 0 END)     AS saldo_mora_30,
           SUM(CASE WHEN c.dias_mora > 90 THEN c.saldo_capital ELSE 0 END)     AS saldo_mora_90
    FROM fact_cartera c
    JOIN dim_fecha f ON f.fecha_key = c.corte_key
    GROUP BY f.anio_mes
),
recaudo AS (
    SELECT f.anio_mes, SUM(p.valor) AS recaudo
    FROM fact_pagos p
    JOIN dim_fecha f ON f.fecha_key = p.fecha_key
    GROUP BY f.anio_mes
),
gestion AS (
    SELECT f.anio_mes,
           COUNT(*)                                            AS gestiones,
           SUM(CASE WHEN g.es_contacto THEN 1 ELSE 0 END)      AS contactos
    FROM fact_gestiones g
    JOIN dim_fecha f ON f.fecha_key = g.fecha_key
    GROUP BY f.anio_mes
),
promesas AS (
    SELECT f.anio_mes,
           COUNT(*)                                            AS promesas_evaluables,
           SUM(CASE WHEN p.cumplida THEN 1 ELSE 0 END)         AS promesas_cumplidas
    FROM fact_promesas p
    JOIN dim_fecha f ON f.fecha_key = p.fecha_promesa_key
    WHERE p.evaluable
    GROUP BY f.anio_mes
)
SELECT c.anio_mes,
       c.obligaciones,
       c.saldo_total,
       c.saldo_vencido,
       c.obligaciones_mora,
       COALESCE(r.recaudo, 0)                                                      AS recaudo,
       COALESCE(g.gestiones, 0)                                                    AS gestiones,
       COALESCE(g.contactos, 0)                                                    AS contactos,
       COALESCE(p.promesas_evaluables, 0)                                          AS promesas_evaluables,
       COALESCE(p.promesas_cumplidas, 0)                                           AS promesas_cumplidas,
       CAST(c.saldo_mora_30 AS DOUBLE PRECISION) / NULLIF(c.saldo_total, 0)        AS par30,
       CAST(c.saldo_mora_90 AS DOUBLE PRECISION) / NULLIF(c.saldo_total, 0)        AS par90,
       CAST(COALESCE(r.recaudo, 0) AS DOUBLE PRECISION)
           / NULLIF(LAG(c.saldo_vencido) OVER (ORDER BY c.anio_mes), 0)            AS tasa_recuperacion,
       CAST(g.contactos AS DOUBLE PRECISION) / NULLIF(g.gestiones, 0)              AS contactabilidad,
       CAST(p.promesas_cumplidas AS DOUBLE PRECISION)
           / NULLIF(p.promesas_evaluables, 0)                                      AS efectividad_promesas
FROM cartera c
LEFT JOIN recaudo  r ON r.anio_mes = c.anio_mes
LEFT JOIN gestion  g ON g.anio_mes = c.anio_mes
LEFT JOIN promesas p ON p.anio_mes = c.anio_mes;

-- 2. Saldo por franja de mora y mes (gráfico de barras apiladas) -----------------------
CREATE VIEW vw_cartera_franja AS
SELECT f.anio_mes,
       c.bucket_mora,
       COUNT(*)             AS obligaciones,
       SUM(c.saldo_capital) AS saldo
FROM fact_cartera c
JOIN dim_fecha f ON f.fecha_key = c.corte_key
GROUP BY f.anio_mes, c.bucket_mora;

-- 3. Roll rates: transición de franja entre cortes consecutivos -------------------------
CREATE VIEW vw_roll_rate AS
WITH cortes AS (
    SELECT corte_key, ROW_NUMBER() OVER (ORDER BY corte_key) AS n
    FROM (SELECT DISTINCT corte_key FROM fact_cartera) d
),
estado AS (
    SELECT c.obligacion_key, k.n, c.bucket_mora
    FROM fact_cartera c
    JOIN cortes k ON k.corte_key = c.corte_key
)
SELECT f.anio_mes                                       AS anio_mes,
       o.bucket_mora                                    AS bucket_origen,
       COALESCE(d.bucket_mora, 'Salida de cartera')     AS bucket_destino,
       COUNT(*)                                         AS obligaciones
FROM estado o
JOIN cortes siguiente ON siguiente.n = o.n + 1
JOIN dim_fecha f ON f.fecha_key = siguiente.corte_key
LEFT JOIN estado d ON d.obligacion_key = o.obligacion_key AND d.n = o.n + 1
GROUP BY f.anio_mes, o.bucket_mora, COALESCE(d.bucket_mora, 'Salida de cartera');

-- 4. Ranking mensual de gestores por recaudo de promesas cumplidas ----------------------
CREATE VIEW vw_ranking_gestores AS
WITH actividad AS (
    SELECT f.anio_mes, g.gestor_key,
           COUNT(*)                                          AS gestiones,
           SUM(CASE WHEN g.es_contacto THEN 1 ELSE 0 END)    AS contactos,
           SUM(CASE WHEN g.es_promesa  THEN 1 ELSE 0 END)    AS promesas
    FROM fact_gestiones g
    JOIN dim_fecha f ON f.fecha_key = g.fecha_key
    GROUP BY f.anio_mes, g.gestor_key
),
resultados AS (
    SELECT f.anio_mes, p.gestor_key,
           SUM(CASE WHEN p.cumplida   THEN 1 ELSE 0 END)             AS promesas_cumplidas,
           SUM(CASE WHEN p.evaluable  THEN 1 ELSE 0 END)             AS promesas_evaluables,
           SUM(CASE WHEN p.cumplida   THEN p.valor_pagado ELSE 0 END) AS recaudo_promesas
    FROM fact_promesas p
    JOIN dim_fecha f ON f.fecha_key = p.fecha_gestion_key
    GROUP BY f.anio_mes, p.gestor_key
)
SELECT a.anio_mes,
       dg.id_gestor,
       dg.nombre,
       dg.equipo,
       a.gestiones,
       a.contactos,
       a.promesas,
       COALESCE(r.promesas_cumplidas, 0)                                           AS promesas_cumplidas,
       COALESCE(r.recaudo_promesas, 0)                                             AS recaudo_promesas,
       CAST(a.contactos AS DOUBLE PRECISION) / NULLIF(a.gestiones, 0)              AS contactabilidad,
       CAST(r.promesas_cumplidas AS DOUBLE PRECISION)
           / NULLIF(r.promesas_evaluables, 0)                                      AS efectividad_promesas,
       DENSE_RANK() OVER (PARTITION BY a.anio_mes
                          ORDER BY COALESCE(r.recaudo_promesas, 0) DESC)           AS ranking
FROM actividad a
JOIN dim_gestor dg ON dg.gestor_key = a.gestor_key
LEFT JOIN resultados r ON r.anio_mes = a.anio_mes AND r.gestor_key = a.gestor_key;
