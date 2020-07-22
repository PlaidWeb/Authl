all: setup format mypy cov pylint flake8 doc

.PHONY: setup
setup:
	poetry install

.PHONY: format
format:
	poetry run isort -y
	poetry run autopep8 -r --in-place .

.PHONY: pylint
pylint:
	poetry run pylint authl tests

.PHONY: flake8
flake8:
	poetry run flake8

.PHONY: mypy
mypy:
	poetry run mypy -p authl -m test --ignore-missing-imports

.PHONY: preflight
preflight:
	@echo "Checking commit status..."
	@git status --porcelain | grep -q . \
		&& echo "You have uncommitted changes" 1>&2 \
		&& exit 1 || exit 0
	@echo "Checking branch..."
	@[ "$(shell git rev-parse --abbrev-ref HEAD)" != "main" ] \
		&& echo "Can only build from main" 1>&2 \
		&& exit 1 || exit 0
	@echo "Checking upstream..."
	@git fetch \
		&& [ "$(shell git rev-parse main)" != "$(shell git rev-parse main@{upstream})" ] \
		&& echo "main differs from upstream" 1>&2 \
		&& exit 1 || exit 0

.PHONY: test
test:
	poetry run coverage run -m pytest -v -Werror

.PHONY: cov
cov: test
	poetry run coverage html
	poetry run coverage report

.PHONY: version
version:
	# Kind of a hacky way to get the version updated, until the poetry folks
	# settle on a better approach
	printf '""" version """\n__version__ = "%s"\n' \
		`poetry version | cut -f2 -d\ ` > authl/__version__.py

.PHONY: build
build: version preflight pylint flake8
	poetry build

.PHONY: clean
clean:
	rm -rf build dist .mypy_cache __pycache__ docs/_build

.PHONY: upload
upload: clean build
	poetry publish

.PHONY: doc
doc:
	poetry run sphinx-build -b html docs/ docs/_build
