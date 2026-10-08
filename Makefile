# SAM calls build-<LogicalId> with ARTIFACTS_DIR set. Code and dependencies are built separately
# so the function zips stay small and only contain what Lambda needs.

APP = saans config fixtures

build-DepsLayer:
	uv export --no-dev --no-hashes --no-emit-project -o requirements.txt -q
	uv pip install -q --target "$(ARTIFACTS_DIR)/python" --python-platform aarch64-manylinux2014 \
		--python-version 3.12 --only-binary :all: -r requirements.txt

build-WorkerFunction:
	cp -R $(APP) "$(ARTIFACTS_DIR)/"
	find "$(ARTIFACTS_DIR)" -name __pycache__ -prune -exec rm -rf {} +

build-ApiFunction: build-WorkerFunction

test:
	uv run pytest -q

plan:
	uv run python -m saans.plan --school demo-1 --replay 2024-11-18

.PHONY: build-DepsLayer build-WorkerFunction build-ApiFunction test plan
