all: format pylint flake8

.PHONY: format
format:
	pipenv run autopep8 -r --in-place .

.PHONY: pylint
pylint:
	pipenv run pylint authl

.PHONY: flake8
flake8:
	pipenv run flake8

.PHONY: build
build: pylint flake8
	pipenv run python3 setup.py sdist
	pipenv run python3 setup.py bdist_wheel

.PHONY: clean
clean:
	rm -rf build dist

.PHONY: upload
upload: clean build
	pipenv run twine upload dist/*
