.PHONY: install lint typecheck test migrate run provision

install:
	pip install -e ".[dev]" 2>/dev/null || pip install -r requirements-dev.txt

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

typecheck:
	mypy src/

test:
	pytest tests/ -v

migrate:
	python -c "import asyncio; from src.gitprbot.db.connection import init_db; asyncio.run(init_db())"

run:
	python -m gitprbot.main

provision:
	python scripts/provision_repo.py $(REPO)
