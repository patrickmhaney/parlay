.PHONY: help css run test sync grade migrate lint backup login-link shots

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  %-10s %s\n", $$1, $$2}'

css: ## Rebuild Tailwind (needs tools/tailwindcss; see README)
	./tools/tailwindcss -c tailwind.config.js -i app/static/css/input.css -o app/static/css/app.css --minify

run: ## Run the dev server on :8080
	.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload

test: ## Run the test suite
	.venv/bin/python -m pytest -q

sync: ## Pull the current season's schedule, odds and scores
	.venv/bin/python scripts/sync_games.py --live

grade: ## Grade every pick whose game is final
	.venv/bin/python scripts/grade.py

migrate: ## Re-import the legacy archives (idempotent)
	.venv/bin/python scripts/migrate_history.py

backup: ## Snapshot the database to backups/
	@mkdir -p backups
	@cp data/parlay.duckdb backups/parlay-$$(date +%Y%m%d%H%M%S).duckdb
	@echo "backed up to backups/"

login-link: ## Print the newest sign-in link (EMAIL_PROVIDER=console)
	@f=$$(ls -t data/outbox/*login* 2>/dev/null | head -1); \
	 if [ -z "$$f" ]; then echo "No links yet — request one at /login first."; \
	 else grep -o 'https\?://[^ ]*token=[A-Za-z0-9_-]*' "$$f"; fi

shots: ## Screenshot every screen (phone+desktop, light+dark) into shots/
	.venv/bin/python scripts/screenshots.py --out shots
