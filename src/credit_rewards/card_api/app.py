from __future__ import annotations

import os
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request, Response

from credit_rewards.datastore.db import session
from credit_rewards.datastore.repository import CardDataRepository
from credit_rewards.awardwallet_compat import build_cards_response, to_awardwallet_card
from credit_rewards.ingest.awardwallet_sync import load_awardwallet_by_registry_key
from credit_rewards.ingest.scrape.registry import load_card_registry

app = FastAPI(
    title="PayCue CardData API",
    description="Rewards CC–compatible credit card data API (own dataset)",
    version="0.1.0",
)

MONTHLY_LIMIT = int(os.getenv("CREDITREWARDS_API_MONTHLY_LIMIT", "2500"))
DEFAULT_SKEY = os.getenv("CREDITREWARDS_DEFAULT_SKEY", "dev")


def _awardwallet_point_values() -> dict[str, float]:
    try:
        return load_awardwallet_by_registry_key(load_card_registry())
    except Exception:
        return {}


def _with_repo(handler: Callable[[CardDataRepository, str], Any], request: Request) -> Any:
    skey = request.headers.get("x-skey") or DEFAULT_SKEY
    path = request.url.path
    with session() as conn:
        repo = CardDataRepository(conn)
        try:
            result = handler(repo, skey)
            repo.log_call(skey, path, 200)
            return result
        except HTTPException as exc:
            repo.log_call(skey, path, exc.status_code)
            raise


@app.get("/")
def root() -> dict[str, str]:
    return {
        "service": "PayCue CardData API",
        "docs": "/docs",
        "compatible_with": "https://rewardscc.com/docs/",
    }


@app.get("/creditcard-cardlist")
def card_list(request: Request) -> list[dict[str, Any]]:
    return _with_repo(lambda repo, _skey: repo.get_card_list(), request)


@app.get("/creditcard-detail-bycard/{card_key}")
def card_detail(card_key: str, request: Request) -> list[dict[str, Any]]:
    def handler(repo: CardDataRepository, _skey: str) -> list[dict[str, Any]]:
        detail = repo.get_card_detail(card_key)
        if not detail:
            raise HTTPException(status_code=404, detail=f"Card not found: {card_key}")
        return detail

    return _with_repo(handler, request)


@app.get("/creditcard-detail-namesearch/{name}")
def search_by_name(name: str, request: Request) -> list[dict[str, Any]]:
    return _with_repo(lambda repo, _skey: repo.search_cards(name), request)


@app.get("/creditcard-spendbonuscategory-categorylist/")
def category_list(request: Request) -> list[dict[str, Any]]:
    return _with_repo(lambda repo, _skey: repo.get_category_list(), request)


@app.get("/creditcard-spendbonuscategory-categorycard/{category_id}")
def category_cards(category_id: int, request: Request) -> list[dict[str, Any]]:
    def handler(repo: CardDataRepository, _skey: str) -> list[dict[str, Any]]:
        rows = repo.get_category_cards(category_id)
        if not rows:
            raise HTTPException(status_code=404, detail=f"Category not found: {category_id}")
        return rows

    return _with_repo(handler, request)


@app.get("/creditcard-pointtransfer-transferprogramlist/")
def transfer_program_list(request: Request) -> list[dict[str, Any]]:
    return _with_repo(lambda repo, _skey: repo.get_transfer_program_list(), request)


@app.get("/creditcard-pointtransfer-transferprogramcard/{partner_id}")
def transfer_program_cards(partner_id: int, request: Request) -> list[dict[str, Any]]:
    def handler(repo: CardDataRepository, _skey: str) -> list[dict[str, Any]]:
        rows = repo.get_transfer_program_cards(partner_id)
        if not rows:
            raise HTTPException(status_code=404, detail=f"Transfer partner not found: {partner_id}")
        return rows

    return _with_repo(handler, request)


@app.get("/creditcard-earnbonus-cards/")
def earnbonus_cards_list(request: Request) -> dict[str, Any]:
    def handler(repo: CardDataRepository, _skey: str) -> dict[str, Any]:
        details = repo.get_all_card_details()
        if not details:
            raise HTTPException(status_code=404, detail="No cards in database")
        return build_cards_response(details, aw_point_values=_awardwallet_point_values())

    return _with_repo(handler, request)


@app.get("/creditcard-earnbonus-bycard/{card_key}")
def earnbonus_by_card(card_key: str, request: Request) -> dict[str, Any]:
    def handler(repo: CardDataRepository, _skey: str) -> dict[str, Any]:
        detail = repo.get_card_detail(card_key)
        if not detail:
            raise HTTPException(status_code=404, detail=f"Card not found: {card_key}")
        aw_values = _awardwallet_point_values()
        card = to_awardwallet_card(
            detail[0],
            awardwallet_point_value=aw_values.get(card_key),
        )
        return {"cards": [card], "meta": build_cards_response([detail[0]])["meta"]}

    return _with_repo(handler, request)


@app.get("/creditcard-mcc-lookup/{mcc_code}")
def mcc_lookup(mcc_code: str, request: Request) -> dict[str, Any]:
    from credit_rewards.mcc_mapping import lookup_mcc_category, mcc_match_to_dict

    def handler(_repo: CardDataRepository, _skey: str) -> dict[str, Any]:
        try:
            match = lookup_mcc_category(mcc_code)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return mcc_match_to_dict(match)

    return _with_repo(handler, request)


@app.get("/creditcard-valuation-programlist/")
def valuation_program_list(request: Request) -> list[dict[str, Any]]:
    return _with_repo(lambda repo, _skey: repo.get_program_valuation_list(), request)


@app.get("/creditcard-valuation-bycard/{card_key}")
def valuation_by_card(card_key: str, request: Request) -> list[dict[str, Any]]:
    def handler(repo: CardDataRepository, _skey: str) -> list[dict[str, Any]]:
        summary = repo.get_card_valuation(card_key)
        if not summary:
            raise HTTPException(status_code=404, detail=f"Card not found: {card_key}")
        return [summary]

    return _with_repo(handler, request)


@app.get("/creditcard-apiusage/{skey}")
def api_usage(skey: str, request: Request) -> list[dict[str, Any]]:
    # Usage endpoint does not count against limit (mirrors Rewards CC behavior)
    with session() as conn:
        repo = CardDataRepository(conn)
        return repo.get_api_usage(skey, MONTHLY_LIMIT)


@app.middleware("http")
async def add_compat_headers(request: Request, call_next: Callable) -> Response:
    response = await call_next(request)
    response.headers["X-PayCue-Data-API"] = "0.1.0"
    return response
