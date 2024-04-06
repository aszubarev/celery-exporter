isort:
	isort .

lint:
	flake8 celery_exporter
	mypy celery_exporter

clean:
	@rm -rf .mypy_cache || true
	@rm -rf .vscode || true
