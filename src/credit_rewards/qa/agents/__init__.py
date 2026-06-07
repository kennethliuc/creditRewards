"""Production QA sub-agents (supervised by qa.supervisor)."""

from credit_rewards.qa.agents.auth_api import AuthApiAgent
from credit_rewards.qa.agents.aux_pages import AuxPagesAgent
from credit_rewards.qa.agents.browser_ui import BrowserUiAgent
from credit_rewards.qa.agents.cards import CardsAgent
from credit_rewards.qa.agents.catalog_recommend import CatalogRecommendAgent
from credit_rewards.qa.agents.infra import InfraAgent
from credit_rewards.qa.agents.merchants import MerchantsAgent

ALL_AGENTS = [
    InfraAgent(),
    CardsAgent(),
    MerchantsAgent(),
    CatalogRecommendAgent(),
    AuthApiAgent(),
    AuxPagesAgent(),
    BrowserUiAgent(),
]
