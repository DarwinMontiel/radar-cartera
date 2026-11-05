# Política de seguridad

## Reportar una vulnerabilidad

No abras un issue público: usa **Security → Report a vulnerability** (reporte privado de GitHub).

## Datos

- Este repositorio **no contiene datos reales**: todo se genera con `cartera generate`.
- En un entorno real, los exportes de origen contienen datos personales protegidos por la
  Ley 1581 de 2012; deben procesarse en infraestructura autorizada y nunca versionarse
  (`data/raw/` y `reports/` están en `.gitignore`).
- Las credenciales del data warehouse se pasan por `CARTERA_DATABASE_URL`, nunca en código.
