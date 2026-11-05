-- Consultas analíticas de ejemplo sobre el data warehouse (PostgreSQL).
-- Muestran funciones de ventana, CTEs y agregaciones condicionales usadas en cobranzas.

-- 1. Top 10 obligaciones que más empeoraron (días de mora) entre los dos últimos cortes.
WITH ultimos AS (
    SELECT DISTINCT corte_key FROM fact_cartera ORDER BY corte_key DESC LIMIT 2
),
evolucion AS (
    SELECT c.obligacion_key,
           c.corte_key,
           c.dias_mora,
           c.dias_mora - LAG(c.dias_mora) OVER (PARTITION BY c.obligacion_key ORDER BY c.corte_key) AS delta_mora
    FROM fact_cartera c
    WHERE c.corte_key IN (SELECT corte_key FROM ultimos)
)
SELECT o.id_obligacion, cl.nombre, o.producto, e.dias_mora, e.delta_mora
FROM evolucion e
JOIN dim_obligacion o ON o.obligacion_key = e.obligacion_key
JOIN dim_cliente cl ON cl.cliente_key = o.cliente_key
WHERE e.delta_mora IS NOT NULL
ORDER BY e.delta_mora DESC
LIMIT 10;

-- 2. Recaudo acumulado del año y participación de cada mes (running total).
SELECT f.anio_mes,
       SUM(p.valor)                                                    AS recaudo_mes,
       SUM(SUM(p.valor)) OVER (PARTITION BY f.anio ORDER BY f.anio_mes) AS recaudo_acumulado,
       ROUND(100.0 * SUM(p.valor) / SUM(SUM(p.valor)) OVER (PARTITION BY f.anio), 2) AS participacion_pct
FROM fact_pagos p
JOIN dim_fecha f ON f.fecha_key = p.fecha_key
GROUP BY f.anio, f.anio_mes
ORDER BY f.anio_mes;

-- 3. Cosechas (vintage): PAR30 actual por trimestre de desembolso y producto.
WITH ultimo AS (SELECT MAX(corte_key) AS corte_key FROM fact_cartera)
SELECT o.producto,
       EXTRACT(YEAR FROM o.fecha_desembolso) || '-T' || EXTRACT(QUARTER FROM o.fecha_desembolso) AS cosecha,
       COUNT(*)                                                                   AS obligaciones,
       ROUND(SUM(CASE WHEN c.dias_mora > 30 THEN c.saldo_capital ELSE 0 END)
             / NULLIF(SUM(c.saldo_capital), 0), 4)                                AS par30
FROM fact_cartera c
JOIN ultimo u ON u.corte_key = c.corte_key
JOIN dim_obligacion o ON o.obligacion_key = c.obligacion_key
GROUP BY o.producto, cosecha
ORDER BY o.producto, cosecha;

-- 4. Días entre la promesa y el pago efectivo (solo promesas cumplidas).
SELECT g.nombre AS gestor,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY fp.fecha - fpr.fecha) AS mediana_dias_antes_de_promesa
FROM fact_promesas pr
JOIN dim_fecha fpr ON fpr.fecha_key = pr.fecha_promesa_key
JOIN fact_pagos p ON p.obligacion_key = pr.obligacion_key
JOIN dim_fecha fp ON fp.fecha_key = p.fecha_key
JOIN dim_gestor g ON g.gestor_key = pr.gestor_key
WHERE pr.cumplida
  AND fp.fecha BETWEEN fpr.fecha - INTERVAL '10 days' AND fpr.fecha + INTERVAL '3 days'
GROUP BY g.nombre
ORDER BY mediana_dias_antes_de_promesa;

-- 5. Clientes con más de una obligación en mora (riesgo de concentración).
SELECT cl.documento, cl.nombre, cl.segmento,
       COUNT(*) FILTER (WHERE c.en_mora)                     AS obligaciones_en_mora,
       SUM(c.saldo_capital) FILTER (WHERE c.en_mora)         AS saldo_vencido
FROM fact_cartera c
JOIN dim_cliente cl ON cl.cliente_key = c.cliente_key
WHERE c.corte_key = (SELECT MAX(corte_key) FROM fact_cartera)
GROUP BY cl.documento, cl.nombre, cl.segmento
HAVING COUNT(*) FILTER (WHERE c.en_mora) > 1
ORDER BY saldo_vencido DESC;
