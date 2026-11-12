# Guía de contribución

1. Rama desde `main`: `feat/…`, `fix/…`, `docs/…`.
2. `make install` y luego `make lint test` antes de cada PR.
3. Commits con [Conventional Commits](https://www.conventionalcommits.org/es/).

## Reglas del proyecto

- **Un KPI, una definición:** cualquier cambio de fórmula se hace en `kpis.py`, `sql/views.sql`,
  `powerbi/medidas.dax` y `docs/kpis.md` en el mismo PR. Las pruebas comparan pandas vs. SQL.
- **Nada se descarta en silencio:** toda regla de calidad nueva va a `quality.py` con severidad
  explícita, prueba y documentación en `docs/calidad-de-datos.md`.
- Las vistas SQL usan solo SQL estándar (deben correr en SQLite y PostgreSQL).
- Cobertura mínima en CI: 90 %.
