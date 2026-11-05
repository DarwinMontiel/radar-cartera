# Diccionario de KPIs

Cada indicador tiene **una sola definición** implementada tres veces: en pandas
(`src/cartera_analytics/kpis.py`), en SQL (`src/cartera_analytics/sql/views.sql`) y en DAX
(`powerbi/medidas.dax`). Las pruebas verifican que pandas y SQL dan el mismo resultado sobre los
mismos datos, en SQLite (unitarias) y en PostgreSQL (integración).

| KPI | Fórmula | Granularidad | Lectura |
|---|---|---|---|
| **Saldo total** | Σ `saldo_capital` del corte | Corte mensual | Tamaño de la cartera administrada |
| **Saldo vencido** | Σ `saldo_capital` con `dias_mora > 0` | Corte mensual | Cartera que requiere gestión de cobro |
| **PAR30** | Σ saldo con mora > 30 días ÷ saldo total | Corte mensual | *Portfolio at Risk*: principal indicador de riesgo |
| **PAR90** | Σ saldo con mora > 90 días ÷ saldo total | Corte mensual | Riesgo de deterioro / castigo |
| **Recaudo** | Σ `valor` de pagos válidos del mes calendario | Mes de `fecha_pago` | Dinero recuperado por cobranza |
| **Tasa de recuperación** | Recaudo del mes ÷ saldo vencido del **corte anterior** | Mes | Qué porción de lo vencido se logró recuperar |
| **Contactabilidad** | Gestiones con contacto ÷ gestiones | Mes de `fecha_gestion` | Calidad de datos de contacto y estrategia de canal |
| **Efectividad de promesas** | Promesas cumplidas ÷ promesas **evaluables** | Mes de `fecha_promesa` | Calidad de la negociación |
| **Roll rate** | % de obligaciones que pasan de la franja *i* (corte anterior) a la *j* (corte actual) | Par de cortes | Velocidad de deterioro o cura de la cartera |
| **Ranking de gestores** | `DENSE_RANK` por recaudo de promesas cumplidas | Mes de `fecha_gestion` | Productividad del equipo |

## Reglas de negocio

### Franjas de mora (aging)

| Franja | Días de mora |
|---|---|
| Al día | 0 |
| 1-30 | 1 a 30 |
| 31-60 | 31 a 60 |
| 61-90 | 61 a 90 |
| 91-180 | 91 a 180 |
| >180 | más de 180 |

Una obligación que está en un corte y no aparece en el siguiente se clasifica como
**Salida de cartera** (cancelada o castigada) en la matriz de roll rate.

### Promesa de pago cumplida

Una promesa se considera **cumplida** si la suma de los pagos de la misma obligación, desde el
día de la gestión hasta `fecha_promesa + 3 días de gracia`, es **≥ 90 %** del valor prometido.

Solo es **evaluable** si su ventana ya cerró en la fecha de corte; las promesas con ventana
abierta no entran en el denominador (contarlas como incumplidas castigaría injustamente a los
gestores al final de cada mes).

### Contacto

Son contacto: *Contacto titular*, *Contacto tercero*, *Promesa de pago* y *Rehúsa pago*.
No son contacto: *No contesta*, *Buzón de voz* y *Número errado*.

## Por qué la tasa de recuperación usa el corte anterior

El recaudo de octubre se obtiene gestionando la cartera que estaba vencida **al cierre de
septiembre**. Dividir por el saldo vencido de octubre mezclaría causa y efecto: las obligaciones
que se normalizaron gracias al pago ya no estarían en el denominador.
