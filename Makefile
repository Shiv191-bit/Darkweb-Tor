.PHONY: run verify

run:
	./.venv/bin/uvicorn backend.app.main:app --host 127.0.0.1 --port 4173

verify:
	./.venv/bin/python -m pytest backend
