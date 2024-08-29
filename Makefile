.PHONY: typehint
typehint:
	mypy --ignore-missing-imports python/manodc/*.py
.PHONY: lint
lint:
	pylint python/manodc/*.py
.PHONY: checklist
checklist: lint typehint
.PHONY: isort
isort:
	isort python/manodc/*.py
.PHONY: format
format:
	yapf --style='{based_on_style: pep8, indent_width: 4, column_limit=120}' -ir python/manodc/*.py
.PHONY: clean
clean:
	find ./ -type f -name "*.pyc" | xargs rm -fr
	find ./ -type d -name __pycache__ | xargs rm -fr
	find ./ -type d -name .mypy_cache | xargs rm -fr