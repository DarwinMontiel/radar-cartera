# Calidad de datos

Los exportes de los sistemas de origen nunca llegan limpios. El pipeline separa explícitamente
dos etapas:

1. **Limpieza** (`transform.py`): estandariza sin descartar. Documentos sin puntos ni espacios,
   nombres con mayúscula inicial, ciudades y resultados de gestión mapeados al catálogo
   (insensible a tildes y mayúsculas), montos en formato colombiano (`$ 1.234.567,50`) a número,
   fechas ISO / `dd/mm/aaaa` / celdas de Excel a fecha.
2. **Validación** (`quality.py`): reglas declarativas por conjunto de datos. Las de severidad
   **rechazo** envían el registro a **cuarentena** con el motivo; las de severidad **alerta**
   solo se reportan. (En el código, los identificadores son `reject` y `warn`; en el tablero, el
   Excel y `rechazados.csv` se muestran en español.)

Nada se descarta en silencio: cada ejecución deja `reports/rechazados.csv` (registro original
completo + motivo), la hoja *Calidad de datos* del Excel y los conteos en `manifest.json`.

## Reglas

| Conjunto | Regla | Severidad | Por qué |
|---|---|---|---|
| clientes | `cliente_duplicado` | rechazo | Doble exportación del maestro |
| clientes | `documento_invalido` (6–10 dígitos) | rechazo | Identificador inutilizable para cobro |
| clientes | `nombre_vacio` | rechazo | No se puede gestionar |
| clientes | `ciudad_fuera_de_catalogo` | alerta | Afecta reportes geográficos, no la gestión |
| clientes | `segmento_invalido` | rechazo | Rompe la segmentación de estrategias |
| obligaciones | `obligacion_duplicada`, `cliente_inexistente` | rechazo | Integridad referencial |
| obligaciones | `monto_invalido`, `plazo_invalido`, `fecha_desembolso_invalida` | rechazo | Valores fuera de dominio |
| cortes | `corte_duplicado` (obligación + fecha) | rechazo | Duplicaría saldo |
| cortes | `obligacion_inexistente` | rechazo | Integridad referencial |
| cortes | `saldo_negativo`, `dias_mora_invalidos` | rechazo | Valores imposibles |
| pagos | `pago_duplicado` | rechazo | Doble exportación: inflaría el recaudo |
| pagos | `obligacion_inexistente` | rechazo | Pago no aplicable |
| pagos | `valor_invalido` (≤ 0) | rechazo | Las reversiones se procesan por otro flujo |
| pagos | `fecha_pago_invalida` (posterior al corte) | rechazo | Fuera del periodo |
| pagos | `canal_desconocido` | alerta | Solo afecta el análisis por canal |
| gestiones | `gestion_duplicada`, `obligacion_inexistente`, `gestor_inexistente` | rechazo | Integridad |
| gestiones | `resultado_desconocido` | rechazo | No se puede clasificar como contacto |
| gestiones | `fecha_gestion_invalida` (posterior al corte) | rechazo | Error de reloj / digitación |
| gestiones | `promesa_incompleta` | rechazo | Una promesa sin fecha o valor no es evaluable |
| gestiones | `canal_desconocido` | alerta | Solo afecta el análisis por canal |

## Reproceso de un mes pasado (`--as-of`)

`cartera run --as-of 2026-08-31` recalcula el corte de agosto con exportes más recientes. Lo
fechado entre el corte pedido y el último corte del exporte **no es un error**: todavía no había
ocurrido. Por eso queda *fuera de alcance* (`rows_out_of_scope` en `manifest.json`) y no va a
cuarentena. Lo fechado después del último corte del exporte sí es una fecha futura y lo
rechazan `fecha_pago_invalida` y `fecha_gestion_invalida`.

Las reglas se aplican en **orden de dependencia** (clientes → obligaciones → cortes / pagos /
gestiones) para que la integridad referencial se valide contra datos ya depurados.

## Verificación automática

El generador sintético registra cuántas anomalías inyecta de cada tipo. La prueba
`test_all_injected_anomalies_are_quarantined` exige que el pipeline detecte **exactamente**
esa cantidad, por motivo y por conjunto de datos: ni falsos positivos ni anomalías que se escapen.

## Agregar una regla

```python
Rule(
    "valor_atipico",
    "pago menor a 50 veces la cuota",
    lambda d: d["valor"] < 50 * d["cuota"],
    severity="warn",
)
```

Se agrega a la lista del conjunto de datos en `validate_all`, con su prueba en `tests/unit/test_quality.py`.
