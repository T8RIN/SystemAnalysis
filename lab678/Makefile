PYTHON ?= python3.11
VENV ?= .venv
PIP := $(VENV)/bin/python -m pip

.PHONY: install copy-env db-up db-down run-cli run-ui smoke clean

install:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt

copy-env:
	test -f .env || cp .env.example .env

db-up:
	docker compose up -d

db-down:
	docker compose down

run-cli:
	$(VENV)/bin/python rag_postgres.py

run-ui:
	$(VENV)/bin/streamlit run app.py

smoke:
	$(VENV)/bin/python -m compileall app.py rag_postgres.py scripts src

clean:
	find . -name "__pycache__" -type d -prune -exec rm -rf {} +
