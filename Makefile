.PHONY: setup extract build build-live verify site proof all

setup:
	uv sync
	npm ci --prefix site

extract:
	uv run capture extract

build:
	uv run capture build --source snapshot

build-live:
	uv run capture build --source live

verify:
	uv run ruff check src tests
	uv run capture verify-manifest data/snapshot
	uv run pytest -q

site: build
	npm run build --prefix site

proof:
	uv run capture proof

all: setup build verify site
