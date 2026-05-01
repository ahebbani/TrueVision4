SHELL := /bin/bash

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
VENV := $(ROOT)/.venv
PYTHON := $(VENV)/bin/python
PIP := $(VENV)/bin/pip
UVICORN := $(VENV)/bin/uvicorn
INSTALL_STAMP := $(VENV)/.installed
PORT ?= 8080
SERVER_PORT ?= 8008
NAME ?= Developer Face
CONTROLLER_URL ?= http://127.0.0.1:$(PORT)

.PHONY: install setup-pi setup-server run run-face run-audio run-force-both run-display run-server run-server-dev add-face db test checkpoints embeddings backfill-transcripts summarize-meetings backfill-summaries

$(VENV)/bin/python:
	python3 -m venv $(VENV)

$(INSTALL_STAMP): pyproject.toml $(VENV)/bin/python
	$(PIP) install --upgrade pip
	$(PIP) install -e .[dev]
	touch $(INSTALL_STAMP)

install: $(INSTALL_STAMP)

setup-pi: install
	bash scripts/setup_pi.sh

setup-server: install
	bash scripts/setup_server.sh

run: install
	TRUEVISION_FORCE_MODE=auto $(PYTHON) -m truevision_pi.main --host 0.0.0.0 --port $(PORT)

run-face: install
	TRUEVISION_FORCE_MODE=face $(PYTHON) -m truevision_pi.main --host 0.0.0.0 --port $(PORT)

run-audio: install
	TRUEVISION_FORCE_MODE=audio $(PYTHON) -m truevision_pi.main --host 0.0.0.0 --port $(PORT)

run-force-both: install
	TRUEVISION_FORCE_MODE=both $(PYTHON) -m truevision_pi.main --host 0.0.0.0 --port $(PORT)

run-display: install
	TRUEVISION_FORCE_MODE=auto TRUEVISION_DISPLAY_BACKGROUND=camera $(PYTHON) -m truevision_pi.main --host 0.0.0.0 --port $(PORT)

run-server: install
	$(PYTHON) -m truevision_server.app --host 0.0.0.0 --port $(SERVER_PORT)

run-server-dev: run-server

add-face: install
	$(PYTHON) scripts/add_face.py --name "$(NAME)"

db: install
	$(PYTHON) scripts/visualize_db.py

test: install
	$(PYTHON) -m pytest

checkpoints: install
	$(PYTHON) scripts/hardware_checkpoints.py --controller-url $(CONTROLLER_URL)

embeddings: install
	$(PYTHON) scripts/manage_embeddings.py --stats

backfill-transcripts: install
	$(PYTHON) scripts/backfill_transcripts.py

summarize-meetings: install
	$(PYTHON) scripts/summarize_meetings.py

backfill-summaries: install
	$(PYTHON) scripts/backfill_summaries.py
