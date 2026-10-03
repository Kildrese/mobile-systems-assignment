"""Agentic tracker: a hand-written agent loop with enforced budgets, classified API
failures, fetch guardrails, SQLite state and a JSONL trace.

It sits next to the FastAPI app in `backend/` but imports nothing from it and needs
neither Postgres nor Docker. Run it from `backend/` with `uv run python -m tracker run`.
"""
