.PHONY: up down migrate test lint eval

# Load .env so POSTGRES_* vars are available to make targets
-include .env
export

COMPOSE = docker compose -f infra/docker-compose.yml
PSQL    = $(COMPOSE) exec -T postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

up:
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down

migrate:
	@echo "Applying migrations..."
	@for f in backend/db/migrations/*.sql; do \
		echo "  $$f"; \
		$(PSQL) < $$f || exit 1; \
	done
	@echo "Migrations complete."
	@$(PSQL) -c "\dt" 2>&1

test:
	pytest backend/tests
	cd frontend && npx vitest run

lint:
	ruff check backend/
	mypy backend/
	cd frontend && npx eslint src --ext .ts,.tsx

eval:
	python scripts/eval_accuracy.py
