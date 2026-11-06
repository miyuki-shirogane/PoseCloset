PYTHON ?= python3

.PHONY: test check index clean

test:
	$(PYTHON) -m unittest discover -s tests -t . -v

check:
	$(PYTHON) scripts/build_index.py --check

index:
	$(PYTHON) scripts/build_index.py

clean:
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
