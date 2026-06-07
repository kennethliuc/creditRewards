# Official CPP Valuation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Single user-facing `estimated_value_usd` via curated program CPP table (max aggregation + card overrides).

**Architecture:** `official_cpp.yaml` defines programs/overrides; `refresh-official-cpp` writes `program_valuations.official_cpp`; `compute_earn_value()` resolves CPP by card_key at runtime from DB + YAML overrides.

**Tech Stack:** Python, SQLite, YAML, pytest, FastAPI

---

See design: `docs/superpowers/specs/2026-06-02-official-cpp-valuation-design.md`

**Tasks:** YAML + refresh module → schema/DB → valuation engine → API/CLI → tests → docs
