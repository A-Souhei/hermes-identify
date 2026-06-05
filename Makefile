ENTIFIER_DIR := services/entifier
PYTHON       := $(ENTIFIER_DIR)/.venv/bin/python

.PHONY: test test-e2e

# Unit tests — no services or API key required (safe for CI)
test:
	cd $(ENTIFIER_DIR) && $(abspath $(PYTHON)) -m pytest tests/ -v

# End-to-end tests — requires `docker compose up -d` and a real OPENAI_API_KEY
test-e2e:
	cd $(ENTIFIER_DIR) && $(abspath $(PYTHON)) -m pytest tests/ -m e2e -v
