"""Product analytics — trial usage tracking and admin summaries."""

from credit_rewards.analytics.repository import AnalyticsRepository
from credit_rewards.analytics.service import analytics_enabled, ingest_events, trial_summary

__all__ = [
    "AnalyticsRepository",
    "analytics_enabled",
    "ingest_events",
    "trial_summary",
]
