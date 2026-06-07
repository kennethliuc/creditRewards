"""Production QA runner — delegates to QASupervisor."""

from credit_rewards.qa.supervisor import DEFAULT_BASE_URL, run_production_qa

__all__ = ["DEFAULT_BASE_URL", "run_production_qa"]
