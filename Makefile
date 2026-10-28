.PHONY: install demo api test lint web-install web-build

install:
	python -m pip install -e ".[dev,eval]"

demo:
	python scripts/bootstrap_demo.py

api: demo
	uvicorn apps.api.app.main:app --reload --host 0.0.0.0 --port 8000

test:
	pytest

lint:
	ruff check .

web-install:
	cd apps/web && npm install

web-build:
	cd apps/web && npm run build

