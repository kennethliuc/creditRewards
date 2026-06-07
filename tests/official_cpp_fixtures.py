"""Official CPP fixtures for tests."""

from credit_rewards.official_cpp import fallback_program_table

EXPECTED_OFFICIAL_CPP = fallback_program_table()


def enrich_from_official_table(card, program_table=None):
    from credit_rewards.official_cpp import enrich_card_profile, resolve_card_official_cpp

    table = program_table or EXPECTED_OFFICIAL_CPP
    detail = {
        "cardKey": card.card_key,
        "baseSpendEarnType": card.reward_program,
        "baseSpendEarnCurrency": card.base_earn_currency,
    }
    cpp, program = resolve_card_official_cpp(card.card_key, detail, table)
    return enrich_card_profile(card, official_cpp=cpp, resolved_program=program)
