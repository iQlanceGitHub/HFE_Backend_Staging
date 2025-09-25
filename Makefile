## Variables ##
SHELL := /bin/bash
export SECRETS_FILE=secrets.json
SRC_FOLDER := src
API_MODULE := src.api.api
VENV_FOLDER := .venv

ENV_FILE ?= .env
CURR_DIR := $(shell pwd)
PORT ?= 8100
HOST ?= 0.0.0.0
WORKERS ?= 1

# Lambdas

now = `date +"%H:%M:%S"`
timestamp = [\033[90m$(now)\033[0m]
log = @echo "$(timestamp) $(1)"

## Rules

all: run

## Run api

run:
	gunicorn ${API_MODULE}:app --workers ${WORKERS} --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8100 --timeout 600 --keep-alive 20

run_local:
	source ${VENV_FOLDER}/bin/activate && \
	python3 -m uvicorn ${API_MODULE}:app \
	--host=0.0.0.0 \
	--port=8100 \
	--workers=1 \
	--proxy-headers \
	--reload & \
	${VENV_FOLDER}/bin/celery -A src.common.celery_worker.celery_app worker --loglevel=info & \
	wait

run_on_docker:
	python3 -m uvicorn ${API_MODULE}:app \
		--host=0.0.0.0 \
		--port=8100 \
		--workers=1 \
		--proxy-headers \
		--reload & \
	celery -A src.common.celery_worker.celery_app worker --loglevel=info & \
	wait

## Install

create_venv:
	$(call log, "Creating virtualenv ...")
	python3 -m venv ${VENV_FOLDER} --prompt fast-api
	$(call log, "Virtualenv created...")


install_dev: create_venv
	$(call log, "Installing dev dependencies ...")
	@ source ${VENV_FOLDER}/bin/activate && pip3 install .[dev]
	$(call log, "Installing dev dependencies Done")

install_on_docker:
	$(call log, "Installing dev dependencies inside docker ...")
	pip3 install .
	$(call log, "Installing dev dependencies inside docker Done")




docker_prepare_local:
	cp secrets_example.json secrets.json
	docker compose up -d
	sh scripts/create_local_queue.sh
	sh scripts/prepare_local_db.sh
	make migrate  

podman_prepare_local:
	cp secrets_example.json secrets.json
	podman compose up -d
	sh scripts/create_local_queue.sh
	sh scripts/prepare_local_db.sh
	make migrate 
## Misc


lint:
	$(call log, "Running linter ...")
	@ source ${VENV_FOLDER}/bin/activate && ruff check --exclude=test . --fix
	$(call log, "Running linter Done")

check_lint:
	$(call log, "Running linter check ...")
	@ source ${VENV_FOLDER}/bin/activate && ruff check --exclude=test .
	$(call log, "Running linter check Done")

format:
	$(call log, "Running formatter ...")
	@ source ${VENV_FOLDER}/bin/activate && ruff format --exclude=test .
	$(call log, "Running formatter Done")

check_format:
	$(call log, "Running formatter check ...")
	@ source ${VENV_FOLDER}/bin/activate && ruff format --exclude=test . --check
	$(call log, "Running formatter check Done")
	

clean:
	$(call log, "Cleaning generated files ...")
	find . -name \*.pyc -delete -o -name \*.pyo -delete -o -name __pycache__ -delete
	rm -f .coverage
	rm -rf htmlcov
	rm -rf dist
	rm -rf build
	rm -rf *.egg-info
	$(call log, "Cleaning generated files Done")

fclean: clean
	$(call log, "Cleaning .venv ...")
	rm -rf ${VENV_FOLDER}
	$(call log, "Cleaning .venv Done")

check_dependencies:
	$(call log, "Checking circular dependencies ...")
	@ source ${VENV_FOLDER}/bin/activate && pycycle --here --ignore ${VENV_FOLDER}
	$(call log, "Checking circular dependencies Done")

redeploy:
	git checkout master
	git pull
	docker ps -a -q --filter ancestor=hfe_backend-fast-api | xargs -r docker stop
	docker ps -a -q --filter ancestor=hfe_backend-fast-api | xargs -r docker rm
	docker rmi hfe_backend-fast-api
	docker-compose up -d




## Database Migrations

init_migration:
	$(call log, "Initializing Alembic migrations...")
	source ${VENV_FOLDER}/bin/activate && alembic init alembic
	$(call log, "Alembic migrations initialized.")

create_migration:
	$(call log, "Creating new migration...")
	 source ${VENV_FOLDER}/bin/activate && alembic revision --autogenerate -m "New migration"
	$(call log, "Migration created.")

migrate:
	$(call log, "Applying migrations...")
	 source ${VENV_FOLDER}/bin/activate && alembic upgrade head
	$(call log, "Migrations applied.")

rollback:
	$(call log, "Rolling back last migration...")
	source ${VENV_FOLDER}/bin/activate && alembic downgrade -1
	$(call log, "Migration rolled back.")


migrate_on_docker:
	$(call log, "Applying migrations...")
	alembic upgrade head
	$(call log, "Migrations applied.")