from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class EarnRule(BaseModel):
    category_name: str
    category_id: int | None = None
    multiplier: float
    description: str = ""
    is_date_limit: bool = False
    limit_begin: date | None = None
    limit_end: date | None = None
    is_spend_limit: bool = False
    spend_limit: float = 0
    spend_limit_reset_period: str = ""


class CardProfile(BaseModel):
    card_key: str
    card_name: str
    card_issuer: str
    reward_program: str
    base_spend_amount: float = 1.0
    base_earn_currency: str = "points"
    cpp_default: float = 1.0
    cpp_cash_floor: float = 1.0
    is_cash_redeemable: bool = False
    official_cpp: float = 1.0
    valuate_as_points: bool = True
    resolved_program: str = ""
    category_rules: list[EarnRule] = Field(default_factory=list)


class Recommendation(BaseModel):
    card_key: str
    card_name: str
    multiplier: float
    points_earned: float
    estimated_value_usd: float
    cpp_used: float
    reason: str
    rank: int
    valuate_as_points: bool = True
    resolved_program: str = ""
    partner_checkout: bool = False
    partner_bonus: bool = False


class PurchaseContext(BaseModel):
    category: str
    amount_usd: float = Field(gt=0)
    as_of: date | None = None
    bonus_categories: list[str] = Field(default_factory=list)
    merchant_id: str | None = None
