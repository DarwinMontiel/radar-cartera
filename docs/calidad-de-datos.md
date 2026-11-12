# Calidad de datos

Los exportes de los sistemas de origen nunca llegan limpios. El pipeline separa explícitamente
dos etapas:

1. **Limpieza** (`transform.py`): estandariza sin descartar. Documentos sin puntos ni espacios,
   nombres con mayúscula inicial, ciudades y resultados de gestión mapeados al catálogo
   (insensible a tildes y mayúsculas), montos en formato colombiano (`$ 1.234.567,50`) a número,
   fechas ISO / `dd/mm/aaaa` / celdas de Excel a fecha.
2. **Validación** (`quality.py`): reglas declarativas por dataset. Las de severidad `reject`
   envían el registro a **cuarentena** con el motivo; las `warn` solo se reportan.

Nada se descarta en silencio: cada ejecución deja `reports/rechazados.csv` (registro original
completo + motivo), la hoja *Calidad de datos* del Excel y los conteos en `manifest.json`.

## Reglas

| Dataset | Regla | Severidad | Por qué |
|---|---|---|---|
| clientes | `cliente_duplicado` | reject | Doble exportación del maestro |
| clientes | `documento_invalido` (6–10 dígitos) | reject | Identificador inutilizable para cobro |
| clientes | `nombre_vacio` | reject | No se puede gestionar |
| clientes | `ciudad_fuera_de_catalogo` | warn | Afecta reportes geográficos, no la gestión |
| clientes | `segmento_invalido` | reject | Rompe la segmentación de estrategias |
| obligaciones | `obligacion_duplicada`, `cliente_inexistente` | reject | Integridad referencial |
| obligaciones | `monto_invalido`, `plazo_invalido`, `fecha_desembolso_invalida` | reject | Valores fuera de dominio |
| cortes | `corte_duplicado` (obligación + fecha) | reject | Duplicaría saldo |
| cortes | `obligacion_inexistente` | reject | Integridad referencial |
| cortes | `saldo_negativo`, `dias_mora_invalidos` | reject | Valores imposibles |
| pagos | `pago_duplicado` | reject | Doble exportación: inflaría el recaudo |
| pagos | `obligacion_inexistente` | reject | Pago no aplicable |
| pagos | `valor_invalido` (≤ 0) | reject | Las reversiones se procesan por otro flujo |
| pagos | `fecha_pago_invalida` (posterior al corte) | reject | Fuera del periodo |
| pagos | `canal_desconocido` | warn | Solo afecta el análisis por canal |
| gestiones | `gestion_duplicada`, `obligacion_inexistente`, `gestor_inexistente` | reject | Integridad |
| gestiones | `resultado_desconocido` | reject | No se puede clasificar como contacto |
| gestiones | `fecha_gestion_invalida` (posterior al corte) | reject | Error de reloj / digitación |
| gestiones | `promesa_incompleta` | reject | Una promesa sin fecha o valor no es evaluable |
| gestiones | `canal_desconocido` | warn | Solo afecta el análisis por canal |

Las reglas se aplican en **orden de dependencia** (clientes → obligaciones → cortes / pagos /
gestiones) para que la integridad referencial se valide contra datos ya depurados.

## Verificación automática

El generador sintético registra cuántas anomalías inyecta de cada tipo. La prueba
`test_all_injected_anomalies_are_quarantined` exige que el pipeline detecte **exactamente**
esa cantidad, por motivo y por dataset: ni falsos positivos ni anomalías que se escapen.

## Agregar una regla

```python
Rule(
    "valor_atipico",
    "pago menor a 50 veces la cuota",
    lambda d: d["valor"] < 50 * d["cuota"],
    severity="warn",
)
```

Se agrega a la lista del dataset en `validate_all`, con su prueba en `tests/unit/test_quality.py`.
