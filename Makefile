.PHONY: install test lint format dashboard extension run clean

install:
	pip install -e ".[dev]"

install-ml:
	pip install -e ".[all]"

test:
	python -m pytest tests/ -q

lint:
	ruff check dot tests

format:
	ruff check dot tests --fix
	ruff format dot tests

dashboard:
	cd dashboard && npm install && npm run build

extension:
	cd vscode-extension && npm install && npm run compile

run:
	python -m dot.cli daemon run

clean:
	rm -rf dist build *.egg-info .pytest_cache .ruff_cache
	rm -rf dashboard/dist dashboard/node_modules
	rm -rf vscode-extension/out vscode-extension/node_modules
