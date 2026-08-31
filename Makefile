.PHONY: install install-ml dev run test lint format docker-build docker-up clean

install:
	pip install -e ".[dev]"

install-ml:
	pip install -r requirements-ml.txt

dev: install install-ml

run:
	uvicorn ad_service.api.main:app --host 0.0.0.0 --port 8000 --reload

test:
	pytest -q

lint:
	ruff check src tests
	mypy src

format:
	ruff format src tests
	ruff check --fix src tests

docker-build:
	docker build -f docker/Dockerfile -t ad-service:cpu .

docker-up:
	docker compose -f docker/docker-compose.yml up --build

clean:
	rm -rf .pytest_cache .ruff_cache .mypy_cache build dist *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
