.DEFAULT_GOAL := help
PY ?= python
DB ?= sqlite:///reports/dw.sqlite

help: ## Lista los comandos disponibles
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install: ## Instala el paquete con dependencias de desarrollo
	$(PY) -m pip install -e ".[dev]"
	pre-commit install || true

lint: ## Ruff + mypy
	ruff check .
	ruff format --check .
	mypy src

test: ## Pruebas con cobertura
	pytest --cov

integration: ## Pruebas contra PostgreSQL (requiere CARTERA_DATABASE_URL)
	pytest -m integration

data: ## Genera exportes sintéticos en data/raw
	cartera generate --out data/raw

muestra: ## Regenera la muestra pública data/muestra (semilla 42, 300 clientes, 6 cortes)
	cartera generate --out data/muestra --seed 42 --clients 300 --months 6

demo: data ## Pipeline completo con DW en SQLite; abre reports/index.html
	cartera run --raw data/raw --out reports --db $(DB)

dw: ## Levanta PostgreSQL y corre el pipeline en Docker
	docker compose up -d postgres
	mkdir -p reports
	# Con el usuario del equipo: en Linux, el de la imagen (uid 10001) no puede escribir en ./reports.
	docker compose run --rm --user "$$(id -u):$$(id -g)" etl

ddl: ## Imprime el DDL de PostgreSQL
	cartera ddl --dialect postgresql

.PHONY: help install lint test integration data muestra demo dw ddl
