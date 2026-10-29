UV ?= uv
MODE ?= regression
.PHONY: setup data test lint typecheck estimate eval eval-live report viewer demo public-demo docker ci
setup:
	$(UV) sync --locked --extra workflow
data:
	$(UV) run --no-sync arh data
test:
	$(UV) run --no-sync pytest
lint:
	$(UV) run --no-sync ruff check src tests scripts
	$(UV) run --no-sync ruff format --check src tests scripts
typecheck:
	$(UV) run --no-sync mypy src
estimate:
	$(UV) run --no-sync arh estimate
eval:
	$(UV) run --no-sync arh eval --mode $(MODE)
eval-live:
	@test -n "$(CONFIG)" -a -n "$(APPROVAL)" || (echo "Explicit CONFIG and APPROVAL paths required; no API calls made."; exit 2)
	$(UV) run --no-sync arh eval-live --config "$(CONFIG)" --approval "$(APPROVAL)"
report:
	$(UV) run --no-sync arh report
viewer:
	$(UV) run --no-sync streamlit run src/agent_reliability/viewer/app.py --server.address 127.0.0.1
demo: viewer
public-demo:
	$(UV) run --no-sync python scripts/build_public_demo.py
docker:
	docker compose up --build -d
ci: data lint typecheck test
	$(UV) run --no-sync arh validate-tasks
	$(UV) run --no-sync arh review-check --packet reviews/benchmark-candidates.json
	$(UV) run --no-sync arh split-check --manifest tasks/grouped-split.proposal.json
	$(UV) run --no-sync arh eval
