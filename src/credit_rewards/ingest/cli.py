from __future__ import annotations

import typer

from credit_rewards.datastore.db import db_path, init_db
from credit_rewards.datastore.repository import CardDataRepository
from credit_rewards.ingest.scrape.issuers import get_scraper
from credit_rewards.ingest.scrape.runner import ScrapeError, refresh_all_cards, scrape_card_entry
from credit_rewards.ingest.bulk_sync import REFERENCE_DIR, bulk_sync_rewardscc
from credit_rewards.ingest.reference_sync import sync_reference
from credit_rewards.ingest.seed_loader import seed_database

app = typer.Typer(help="CardData database init, seed, and scrape tools")


@app.command("init")
def init_cmd() -> None:
    path = init_db()
    typer.echo(f"Initialized database at {path}")


@app.command("seed")
def seed_cmd() -> None:
    """Load category taxonomy + transfer partners (not card rewards — use refresh-all)."""
    counts = seed_database()
    typer.echo(
        f"Seeded taxonomy: {counts['transfer_partners']} transfer partners. "
        "Run `credit-rewards-db refresh-all` to scrape card rewards from issuer sites."
    )


@app.command("refresh")
def refresh_cmd(
    card_key: str = typer.Option(..., help="cardKey from data/card_registry.yaml"),
) -> None:
    """Scrape one card from its issuer website and upsert reward rules."""
    init_db()
    from credit_rewards.datastore.db import session
    from credit_rewards.ingest.scrape.registry import load_card_registry

    entry = next((c for c in load_card_registry() if c["card_key"] == card_key), None)
    if not entry:
        raise typer.BadParameter(f"Unknown card_key: {card_key}")

    with session() as conn:
        detail = scrape_card_entry(CardDataRepository(conn), entry)
    typer.echo(
        f"Scraped {detail['cardName']} — {len(detail.get('spendBonusCategory', []))} earn rules"
    )


@app.command("refresh-all")
def refresh_all_cmd(
    fail_fast: bool = typer.Option(
        False,
        "--fail-fast",
        help="Stop on first scrape error (default: continue and commit each success)",
    ),
) -> None:
    """Scrape all cards in data/card_registry.yaml from issuer websites."""
    init_db()
    from credit_rewards.datastore.db import session
    from credit_rewards.ingest.scrape.registry import load_card_registry

    results: list[dict] = []
    errors: list[str] = []
    for entry in load_card_registry():
        try:
            with session() as conn:
                detail = scrape_card_entry(CardDataRepository(conn), entry)
            results.append(
                {
                    "card_key": entry["card_key"],
                    "rules": len(detail.get("spendBonusCategory") or []),
                }
            )
            typer.echo(f"  ✓ {entry['card_key']}: {results[-1]['rules']} rules")
        except Exception as exc:
            msg = f"{entry['card_key']}: {exc}"
            errors.append(msg)
            typer.echo(f"  ✗ {msg}", err=True)
            if fail_fast:
                raise typer.Exit(1) from exc

    typer.echo(f"Refreshed {len(results)}/{len(load_card_registry())} cards from issuer websites.")
    if errors:
        typer.echo(f"{len(errors)} card(s) failed — reference import still valid for runtime.", err=True)
        raise typer.Exit(1)


@app.command("scrape")
def scrape_cmd(
    card_key: str = typer.Option(..., help="cardKey slug, e.g. amex-gold"),
    url: str = typer.Option(..., help="Issuer public card page URL"),
    parser: str = typer.Option("amex", help="Parser: amex, chase, citi"),
) -> None:
    """Scrape a single ad-hoc URL (for testing new cards before adding to registry)."""
    init_db()
    from credit_rewards.datastore.db import session

    entry = {"card_key": card_key, "url": url, "parser": parser, "issuer": "", "card_network": ""}
    with session() as conn:
        detail = scrape_card_entry(CardDataRepository(conn), entry)
    typer.echo(f"Upserted {detail['cardName']} ({card_key})")


@app.command("info")
def info_cmd() -> None:
    from credit_rewards.datastore.db import session

    path = db_path()
    typer.echo(f"Database: {path}")
    with session() as conn:
        repo = CardDataRepository(conn)
        cards = repo.get_card_list()
        total = sum(len(g["card"]) for g in cards)
        typer.echo(f"Cards loaded: {total}")


@app.command("sync-awardwallet")
def sync_awardwallet_cmd(
    show_expired: bool = typer.Option(False, help="Include expired bonus categories"),
) -> None:
    """
    Pull AwardWallet Credit Card Bonus API cache (commercial credentials required).
    Adds awardWalletPointValue cross-check for local earn-bonus endpoints.
    """
    from credit_rewards.ingest.awardwallet_sync import (
        AWARDWALLET_CACHE_DIR,
        AwardWalletCCError,
        cache_awardwallet_cards,
        fetch_awardwallet_cards,
    )

    try:
        payload = fetch_awardwallet_cards(show_expired=show_expired)
    except AwardWalletCCError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    path = cache_awardwallet_cards(payload)
    count = len(payload.get("cards") or [])
    typer.echo(f"Cached {count} AwardWallet cards → {path}")
    typer.echo(f"Valuation blog: https://awardwallet.com/blog/awardwallet-mile-valuations/")


@app.command("mcc-lookup")
def mcc_lookup_cmd(
    mcc: str = typer.Argument(..., help="Visa MCC code, e.g. 5411"),
) -> None:
    """Map Visa MCC (ISO 18245) to Rewards CC spend bonus category."""
    from credit_rewards.mcc_mapping import lookup_mcc_category

    try:
        match = lookup_mcc_category(mcc)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    typer.echo(f"MCC {match.mcc} — {match.mcc_description}")
    typer.echo(f"  → {match.spend_bonus_category_name} (id {match.spend_bonus_category_id})")
    typer.echo(f"  Group: {match.spend_bonus_category_group} · match={match.match_type}")


@app.command("refresh-official-cpp")
def refresh_official_cpp_cmd() -> None:
    """Recompute official CPP (max of sources) into program_valuations."""
    from credit_rewards.ingest.official_cpp_refresh import refresh_official_cpp

    init_db()
    result = refresh_official_cpp()
    typer.echo(f"Updated official CPP for {result['count']} program(s)")
    for program, row in sorted(result["programs"].items()):
        typer.echo(f"  {program}: {row['official_cpp']}¢ — sources {row['sources']}")


@app.command("valuation-report")
def valuation_report_cmd(
    card_key: list[str] = typer.Option(
        None,
        "--card-key",
        help="Card to show (repeatable). Default: all registry cards",
    ),
) -> None:
    """Show official CPP and single estimated dollar value per card."""
    from credit_rewards.datastore.db import session
    from credit_rewards.ingest.scrape.registry import load_card_registry

    init_db()
    keys = card_key or [c["card_key"] for c in load_card_registry()]

    with session() as conn:
        repo = CardDataRepository(conn)
        program_table = repo.get_official_cpp_table()
        missing = []
        for key in keys:
            summary = repo.get_card_valuation(key)
            if not summary:
                missing.append(key)
                continue
            typer.echo(f"\n{summary['cardName']} ({key})")
            typer.echo(f"  Program: {summary['rewardProgram']}")
            typer.echo(f"  Official CPP: {summary['officialCpp']}¢ → ${summary['dollarPerPoint']:.4f}/pt")
            ex = summary["examplePurchase"]
            typer.echo(
                f"  Example ${ex['amountUsd']:.0f} purchase: ${ex['estimatedValueUsd']:.2f} — {ex['reason']}"
            )

        if missing:
            typer.echo(f"\nMissing {len(missing)} card(s) — run import-reference first:", err=True)
            for key in missing:
                typer.echo(f"  ✗ {key}", err=True)
            raise typer.Exit(1)


@app.command("bulk-sync", hidden=True)
def bulk_sync_cmd(
    force: bool = typer.Option(False, help="Re-fetch even if local file exists"),
    max_calls: int = typer.Option(48000, help="Stop before exceeding this many API calls"),
    i_know: bool = typer.Option(
        False,
        "--i-know-what-im-doing",
        help="Required: confirms you want the full US card catalog (~tens of thousands of API calls)",
    ),
) -> None:
    """
    [Advanced] Download the ENTIRE Rewards CC catalog. NOT needed for this project.
    Use sync-reference instead (registry cards only, ~15–30 API calls).
    """
    from credit_rewards.client import RewardsCCError

    if not i_know:
        typer.echo(
            "bulk-sync pulls every US card (~50k API calls). "
            "For Amex/Chase/Citi in card_registry.yaml, run:\n"
            "  credit-rewards-db sync-reference",
            err=True,
        )
        raise typer.Exit(1)

    typer.echo(f"Bulk sync → {REFERENCE_DIR}")
    typer.echo(f"Quota guard: max {max_calls} API calls (usage endpoint not counted).")
    try:
        manifest = bulk_sync_rewardscc(force=force, max_calls=max_calls)
    except RewardsCCError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    stats = manifest["stats"]
    counts = manifest["counts"]
    typer.echo(f"API calls used: {stats['api_calls']} (skipped cached: {stats['skipped_cached']})")
    typer.echo(f"Categories: {counts['categories']}")
    typer.echo(f"Unique cards: {counts['unique_card_keys']}")
    typer.echo(f"Card detail files: {counts['card_details_on_disk']}")
    if stats["errors"]:
        typer.echo(f"Errors: {len(stats['errors'])} (see bulk_manifest.json)", err=True)
    typer.echo("Done. Develop offline; re-run next month or with --force to refresh.")


@app.command("bulk-status")
def bulk_status_cmd() -> None:
    """Show local Rewards CC cache stats."""
    import json

    manifest_path = REFERENCE_DIR / "bulk_manifest.json"
    if not manifest_path.exists():
        typer.echo("No bulk sync yet. Run: credit-rewards-db bulk-sync")
        raise typer.Exit(1)
    manifest = json.loads(manifest_path.read_text())
    typer.echo(json.dumps(manifest, indent=2))


@app.command("sync-reference")
def sync_reference_cmd(
    card_key: list[str] = typer.Option(
        None,
        "--card-key",
        help="Card to pull (repeatable). Default: all cards in card_registry.yaml",
    ),
) -> None:
    """
    Pull Rewards CC golden JSON for registry cards only (Amex, Chase, Citi, …).
    ~15–30 API calls for the current 5-card wallet — not the full catalog.
    Requires REWARDS_CC_API_KEY in .env (do not paste keys in chat).
    """
    from credit_rewards.client import RewardsCCError

    keys = card_key or None
    try:
        manifest = sync_reference(card_keys=keys)
    except RewardsCCError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc

    typer.echo(f"Reference data saved to {REFERENCE_DIR}")
    typer.echo(f"API calls used: {manifest['api_calls']} (registry scope only)")
    for key, meta in manifest["cards"].items():
        typer.echo(f"  ✓ {key}: {meta['rule_count']} rules ({meta.get('issuer', '')})")
    typer.echo("Next: credit-rewards-db import-reference")


@app.command("import-catalog-wallet")
def import_catalog_wallet_cmd(
    limit: int = typer.Option(0, help="Max cards to import (0 = all catalog)"),
) -> None:
    """Import wallet catalog cards (category snapshots) into SQLite for production recommend."""
    from credit_rewards.card_import import import_catalog_wallet_to_db

    init_db()
    cap = limit if limit > 0 else None
    result = import_catalog_wallet_to_db(limit=cap)
    typer.echo(
        f"Catalog wallet import: {result['imported_count']}/{result['total']} imported, "
        f"{result['skipped_count']} skipped (need live API or sync)"
    )
    if result["skipped_count"] and result["skipped_count"] <= 20:
        for key in result["skipped"]:
            typer.echo(f"  ✗ {key}")


@app.command("import-reference")
def import_reference_cmd(
    card_key: list[str] = typer.Option(
        None,
        "--card-key",
        help="Card to import (repeatable). Default: all registry cards",
    ),
) -> None:
    """Load Rewards CC reference JSON into local CardData API database (aligned data)."""
    from credit_rewards.ingest.reference_import import import_reference_to_db

    init_db()
    keys = card_key or None
    result = import_reference_to_db(card_keys=keys)
    typer.echo(f"Imported {result['count']} card(s) into CardData API database")
    for key in result["imported"]:
        typer.echo(f"  ✓ {key}")
    if result["missing"]:
        typer.echo(f"Missing reference for {len(result['missing'])} card(s) — run sync-reference first:", err=True)
        for key in result["missing"]:
            typer.echo(f"  ✗ {key}", err=True)
        raise typer.Exit(1)

    from credit_rewards.ingest.official_cpp_refresh import refresh_official_cpp

    cpp_result = refresh_official_cpp()
    typer.echo(f"Official CPP refreshed for {cpp_result['count']} program(s)")


@app.command("validate-reference")
def validate_reference_cmd(
    card_key: list[str] = typer.Option(None, "--card-key", help="Card to validate (repeatable)"),
) -> None:
    """Compare local scraped API vs Rewards CC reference JSON."""
    from credit_rewards.ingest.reference_validate import validate_all
    from credit_rewards.ingest.scrape.registry import load_card_registry

    init_db()
    keys = card_key or [c["card_key"] for c in load_card_registry()]
    results = validate_all(keys)
    failed = 0
    for result in results:
        if result.ok:
            typer.echo(f"  ✓ {result.card_key}")
        else:
            failed += 1
            typer.echo(f"  ✗ {result.card_key}", err=True)
            for note in result.notes:
                typer.echo(f"      {note}", err=True)
            for diff in result.diffs:
                typer.echo(f"      {diff.field}: expected {diff.expected}, got {diff.actual}", err=True)

    if failed:
        raise typer.Exit(1)
    typer.echo("All cards match reference within tolerance.")


def _print_comparison_summary(report) -> None:
    if report.aligned:
        typer.echo(f"  ✓ {report.card_key}: aligned ({len(report.matched)} rules)")
        return
    typer.echo(f"  ✗ {report.card_key}: not aligned", err=True)
    for m in report.mismatches:
        typer.echo(f"      [{m.mismatch_type}] {m.explanation}", err=True)
    if report.extra_scraped:
        typer.echo(f"      extra scraped: {len(report.extra_scraped)}", err=True)
    if report.extra_reference:
        typer.echo(f"      extra reference: {len(report.extra_reference)}", err=True)


@app.command("compare")
def compare_cmd(
    card_key: list[str] = typer.Option(..., "--card-key", help="Card to compare (repeatable)"),
    write_json: bool = typer.Option(
        False,
        "--write-json",
        help="Write per-card JSON under data/reports/comparison/",
    ),
) -> None:
    """Compare local scraped data vs Rewards CC reference JSON for given cards."""
    from credit_rewards.ingest.compare import compare_card, write_reports

    init_db()
    failed = 0
    reports = []
    for key in card_key:
        report = compare_card(key)
        reports.append(report)
        if not report.aligned:
            failed += 1
        _print_comparison_summary(report)

    if write_json:
        paths = write_reports(reports)
        typer.echo(f"Wrote {len(paths)} report file(s)")

    if failed:
        raise typer.Exit(1)


@app.command("compare-all")
def compare_all_cmd(
    write_json: bool = typer.Option(
        True,
        "--write-json/--no-write-json",
        help="Write JSON reports to data/reports/comparison/",
    ),
) -> None:
    """Compare all registry cards; exit 1 if any card is not aligned."""
    from credit_rewards.ingest.compare import compare_all, write_reports
    from credit_rewards.ingest.scrape.registry import load_card_registry

    init_db()
    reports = compare_all()
    failed = 0
    for report in reports:
        if not report.aligned:
            failed += 1
        _print_comparison_summary(report)

    aligned = sum(1 for r in reports if r.aligned)
    typer.echo(f"Summary: {aligned}/{len(reports)} aligned")

    if write_json:
        paths = write_reports(reports)
        typer.echo(f"Reports: {paths[0].parent}")

    if failed:
        raise typer.Exit(1)


@app.command("validation-independent")
def validation_independent_cmd(
    reimport: bool = typer.Option(
        True,
        "--reimport/--no-reimport",
        help="Re-import reference before checking (default: yes)",
    ),
) -> None:
    """Phase 1 gates: L1 + L3 + CPP + MCC (no issuer scrape). Monitor must pass this first."""
    from credit_rewards.validation.independent import run_independent_validation

    init_db()
    result = run_independent_validation(reimport_reference=reimport)
    for gate in result.gates:
        mark = "✓" if gate.status == "pass" else "✗"
        typer.echo(f"  {mark} {gate.name}: {gate.detail} ({gate.rate}% ≥ {gate.gate_pct}%)")
    if result.ok:
        typer.echo("Independent validation passed ✅ — Monitor may assign L2 Parser agents")
        return
    typer.echo("Independent validation failed:", err=True)
    for blocker in result.blockers:
        typer.echo(f"  • {blocker}", err=True)
    raise typer.Exit(1)


@app.command("validation-monitor-run")
def validation_monitor_run_cmd(
    max_cycles: int = typer.Option(3, help="Monitor re-check loops before stopping"),
    no_evidence: bool = typer.Option(False, "--no-evidence"),
) -> None:
    """Monitor supervisor: run all core gates until core_ready or max_cycles."""
    import json

    from credit_rewards.validation.monitor_run import run_monitor_until_ready

    init_db()
    result = run_monitor_until_ready(max_cycles=max_cycles, fetch_evidence=not no_evidence)
    typer.echo(json.dumps(result, indent=2))
    if result["core_ready"]:
        typer.echo("\nCore validation complete ✅ — Monitor releases payment UI work.")
        return
    typer.echo(
        f"\nMonitor stop: core_ready=false after {result['cycles_run']} cycle(s). "
        "Dispatch fixers from final.tasks — no user confirmation needed.",
        err=True,
    )
    for blocker in result["final"].get("blockers") or []:
        typer.echo(f"  • {blocker}", err=True)
    raise typer.Exit(1)


@app.command("validation-monitor")
def validation_monitor_cmd(
    include_l2: bool = typer.Option(
        False,
        "--include-l2",
        help="After core gates pass, emit legacy L2 overlay tasks",
    ),
    skip_network: bool = typer.Option(
        False,
        "--skip-network",
        help="Skip live issuer scrape in external track (structure only)",
    ),
    no_evidence: bool = typer.Option(
        False,
        "--no-evidence",
        help="Skip issuer HTML evidence fetch in external track",
    ),
) -> None:
    """Monitor agent: supervise internal + external cross-validation + MCC gap fixers."""
    import json

    from credit_rewards.validation.orchestrator import build_monitor_plan

    init_db()
    plan = build_monitor_plan(
        include_l2=include_l2,
        include_external=True,
        include_mcc_gap=True,
        fetch_evidence=not no_evidence,
        skip_network=skip_network,
    )
    typer.echo(json.dumps(plan, indent=2))
    if plan["phase"] == "core_complete":
        typer.echo("\nCore validation complete ✅ — Monitor may proceed to payment UI.")
        return
    typer.echo(f"\nPhase: {plan['phase']} · dispatch → {plan.get('next_agent')}", err=True)
    for blocker in plan.get("ship_blocked_until") or []:
        typer.echo(f"  • {blocker}", err=True)
    raise typer.Exit(1)


@app.command("payment-ui-monitor")
def payment_ui_monitor_cmd(
    skip_tests: bool = typer.Option(False, "--skip-tests", help="Skip pytest gate"),
) -> None:
    """Monitor agent: supervise payment homepage (merchant + page + API + tests)."""
    import json

    from credit_rewards.payment_ui.orchestrator import build_payment_ui_monitor_plan

    init_db()
    plan = build_payment_ui_monitor_plan(run_pytest=not skip_tests)
    typer.echo(json.dumps(plan, indent=2))
    if plan["page_ready"]:
        typer.echo("\nPayment UI page_ready ✅ — MVP gates pass.")
        return
    typer.echo(f"\nPhase: {plan['phase']} · dispatch fixers:", err=True)
    for task in plan.get("tasks") or []:
        typer.echo(f"  • [{task['agent']}] {task['scope']}", err=True)
    raise typer.Exit(1)


@app.command("payment-ui-monitor-run")
def payment_ui_monitor_run_cmd(
    max_cycles: int = typer.Option(3, help="Monitor re-check loops"),
    skip_tests: bool = typer.Option(False, "--skip-tests"),
) -> None:
    """Monitor supervisor: re-run payment UI gates until page_ready or max_cycles."""
    import json

    from credit_rewards.payment_ui.monitor_run import run_payment_ui_monitor_until_ready

    init_db()
    result = run_payment_ui_monitor_until_ready(
        max_cycles=max_cycles,
        run_pytest=not skip_tests,
    )
    typer.echo(json.dumps(result, indent=2))
    if result["page_ready"]:
        typer.echo("\nPayment UI page_ready ✅")
        return
    typer.echo(
        f"\nMonitor stop: page_ready=false after {result['cycles_run']} cycle(s).",
        err=True,
    )
    raise typer.Exit(1)


@app.command("validation-external")
def validation_external_cmd(
    card_key: list[str] = typer.Option(
        None,
        "--card-key",
        help="Card to validate (repeatable). Default: all registry cards",
    ),
    skip_network: bool = typer.Option(
        False,
        "--skip-network",
        help="Skip live scrape (for CI structure checks)",
    ),
    no_evidence: bool = typer.Option(
        False,
        "--no-evidence",
        help="Skip issuer page evidence fetch",
    ),
    write_report: bool = typer.Option(True, "--write-report/--no-write-report"),
) -> None:
    """External cross-validation: raw issuer scrape vs reference (no overlay)."""
    import json

    from credit_rewards.validation.external import run_external_validation, write_external_report

    init_db()
    keys = card_key or None
    result = run_external_validation(
        card_keys=keys,
        fetch_evidence=not no_evidence,
        skip_network=skip_network,
    )
    typer.echo(
        f"External cross-verify: {result.cross_verified_pct}% "
        f"(gate ≥{result.gate_pct * 100}%) · scraped {result.scraped_count}/20"
    )
    for card in result.cards:
        if not card.scrape_ok:
            typer.echo(f"  ✗ {card.card_key}: {card.scrape_error}", err=True)
        else:
            typer.echo(
                f"  {'✓' if card.cross_verified_pct >= result.gate_pct * 100 else '○'} "
                f"{card.card_key}: {card.cross_verified_pct}% "
                f"({card.cross_verified_rows}/{card.total_rows} rows, raw rules={card.raw_rule_count})"
            )
    if write_report:
        path = write_external_report(result)
        typer.echo(f"Report → {path}")
    if result.ok:
        typer.echo("External validation passed ✅")
        return
    for blocker in result.blockers:
        typer.echo(f"  • {blocker}", err=True)
    raise typer.Exit(1)


@app.command("mcc-gap-report")
def mcc_gap_report_cmd(
    write_report: bool = typer.Option(True, "--write-report/--no-write-report"),
) -> None:
    """MCC → category gap matrix for Phase-1 card earn categories."""
    from credit_rewards.validation.mcc_gap import run_mcc_gap_analysis, write_mcc_gap_report

    init_db()
    result = run_mcc_gap_analysis()
    typer.echo(
        f"Phase-1 categories: {result.total_categories} · "
        f"classified {result.classified_pct}% · "
        f"MCC bonus path {result.mcc_bonus_coverage_pct}% · "
        f"master list {result.master_category_count}"
    )
    gaps = [c for c in result.categories if c.gap]
    typer.echo(f"Gaps (fallback to base earn): {len(gaps)}")
    for row in gaps[:12]:
        typer.echo(f"  • {row.category_name} ({row.card_count} cards) — {row.note}")
    if write_report:
        json_path, md_path = write_mcc_gap_report(result)
        typer.echo(f"Reports → {json_path} · {md_path}")
    if result.ok:
        typer.echo("MCC gap gate passed ✅")
        return
    for blocker in result.blockers:
        typer.echo(f"  • {blocker}", err=True)
    raise typer.Exit(1)


@app.command("validation-report")
def validation_report_cmd(
    skip_scrape: bool = typer.Option(
        False,
        "--skip-scrape",
        help="Skip live issuer scrape (L2 issuer cross-check only)",
    ),
    no_evidence: bool = typer.Option(
        False,
        "--no-evidence",
        help="Skip fetching issuer HTML for compare evidence",
    ),
) -> None:
    """Run full validation (V0–V5) and write reports/validation + docs/validation/status.md."""
    from credit_rewards.validation.report import run_validation_report

    init_db()
    summary = run_validation_report(
        fetch_evidence=not no_evidence,
        skip_scrape=skip_scrape,
    )
    typer.echo(f"Validation report → {summary['output_dir']}")
    typer.echo(f"Status doc → {summary['status_path']}")
    typer.echo(f"L1 {summary['l1']} · L3 {summary['l3']} · scraped {summary['scraped']}/20")
    if summary["scrape_failed"]:
        typer.echo(f"Scrape failures: {summary['scrape_failed']}", err=True)
    if summary["ship_ready"]:
        typer.echo("Ship ready ✅")
    elif summary.get("independent_ok"):
        typer.echo("Independent validation OK ✅ · Full ship blocked on L2", err=True)
        for blocker in summary.get("l2_blockers") or []:
            typer.echo(f"  • {blocker}", err=True)
        raise typer.Exit(2)
    else:
        typer.echo("Not ship ready — see blockers in docs/validation/status.md", err=True)
        for blocker in summary["blockers"]:
            typer.echo(f"  • {blocker}", err=True)
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
