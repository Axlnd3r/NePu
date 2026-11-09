.PHONY: setup extract build build-live verify site serve qa proof all

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
	uv run capture verify-manifest data/reference
	uv run capture verify-manifest data/prereg
	uv run pytest -q

site: build
	npm run build --prefix site

# Serves site/out at http://localhost:8000 (the export uses absolute paths, so file:// breaks it).
serve:
	uv run python -m http.server 8000 --directory site/out

# Opens every page of site/out in Chrome (desktop light/dark, phone); needs `make site` first.
qa:
	node qa/check.mjs

proof:
	uv run capture proof commit

all: setup build verify site
