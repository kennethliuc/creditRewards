"""Browser UI agent — every user-facing operation via Playwright."""

from __future__ import annotations

from credit_rewards.qa.agents.base import BaseQAAgent, url
from credit_rewards.qa.models import QAContext, QAAgentReport, QAResult


class BrowserUiAgent(BaseQAAgent):
    agent_id = "browser"
    agent_name = "Browser UI Agent"

    def run(self, ctx: QAContext) -> QAAgentReport:
        if not ctx.run_browser:
            return QAAgentReport(
                agent_id=self.agent_id,
                agent_name=self.agent_name,
                results=[
                    QAResult("UI-*", "E", "Browser track", "skip", "Skipped (--no-browser)"),
                ],
            )
        return self._wrap(ctx, self._checks)

    def _seed_wallet(self, page, cards=None) -> None:
        cards = cards or [
            {"card_key": "amex-gold", "card_name": "Amex Gold", "issuer": "Amex"},
            {"card_key": "chase-sapphirepreferred", "card_name": "Sapphire", "issuer": "Chase"},
        ]
        page.evaluate(
            """(payload) => {
            localStorage.setItem('paycue_lang_v1', payload.lang);
            localStorage.setItem('paycue_wallet_v1', JSON.stringify({ cards: payload.cards }));
            localStorage.setItem('paycue_pay_tab_v1', payload.tab);
          }""",
            {"lang": "en", "cards": cards, "tab": "name"},
        )

    def _checks(self, ctx: QAContext) -> list[QAResult]:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            return [
                QAResult(
                    "UI-*",
                    "E",
                    "Browser track",
                    "skip",
                    "pip install -e '.[qa]' && playwright install chromium",
                )
            ]

        results: list[QAResult] = []
        base = ctx.base_url

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 390, "height": 844})
            page = context.new_page()

            # UI-01 Languages
            for lang, code in [("English", "en"), ("Español", "es"), ("中文", "zh")]:
                try:
                    page.goto(base, wait_until="networkidle", timeout=45000)
                    page.evaluate("localStorage.clear()")
                    page.reload(wait_until="networkidle")
                    page.locator(f".lang-btn[data-lang='{code}']").click()
                    page.wait_for_timeout(400)
                    visible = page.locator("#view-local-setup").is_visible()
                    results.append(
                        QAResult(f"UI-LANG-{code}", "E", f"Language pick {lang}", "pass" if visible else "fail", code)
                    )
                except Exception as exc:
                    results.append(QAResult(f"UI-LANG-{code}", "E", f"Language pick {lang}", "fail", str(exc)[:120]))

            # UI-02 Setup flow
            try:
                page.goto(base, wait_until="networkidle")
                self._seed_wallet(page, cards=[])
                page.evaluate("localStorage.removeItem('paycue_wallet_v1')")
                page.evaluate("localStorage.setItem('paycue_lang_v1','en')")
                page.reload(wait_until="networkidle")
                page.locator("#view-local-setup").wait_for(state="visible", timeout=8000)
                tiles = page.locator("#localCardPicker .card-tile")
                if tiles.count() > 0:
                    tiles.first.click()
                page.locator("#localSave").click()
                page.locator("#view-pay").wait_for(state="visible", timeout=8000)
                results.append(QAResult("UI-02", "E", "Onboarding pick card + start", "pass", "pay view shown"))
            except Exception as exc:
                results.append(QAResult("UI-02", "E", "Onboarding pick card + start", "fail", str(exc)[:160]))

            # UI-03 Pay tabs
            try:
                page.goto(base, wait_until="networkidle")
                self._seed_wallet(page)
                page.reload(wait_until="networkidle")
                page.locator("#view-pay").wait_for(state="visible")
                page.locator('.tab[data-tab="url"]').click()
                url_visible = page.locator("#panel-url.active").count() > 0
                page.locator('.tab[data-tab="name"]').click()
                name_visible = page.locator("#panel-name.active").count() > 0
                ok = url_visible and name_visible
                results.append(QAResult("UI-03", "E", "Pay tabs online/in-store", "pass" if ok else "fail", f"url={url_visible} store={name_visible}"))
            except Exception as exc:
                results.append(QAResult("UI-03", "E", "Pay tabs online/in-store", "fail", str(exc)[:120]))

            # UI-04 Location hint
            try:
                page.locator('.tab[data-tab="name"]').click()
                loc = page.locator("#locationStatus")
                results.append(
                    QAResult(
                        "UI-04",
                        "E",
                        "Location hint (in-store)",
                        "pass" if loc.is_visible() else "warn",
                        (loc.inner_text() or "")[:80],
                    )
                )
            except Exception as exc:
                results.append(QAResult("UI-04", "E", "Location hint", "fail", str(exc)[:120]))

            # UI-05 Nearby chips (mock GPS)
            try:
                geo_ctx = browser.new_context(
                    geolocation={"latitude": 30.2672, "longitude": -97.7431},
                    permissions=["geolocation"],
                    viewport={"width": 390, "height": 844},
                )
                gpage = geo_ctx.new_page()
                gpage.goto(base, wait_until="networkidle")
                self._seed_wallet(gpage)
                gpage.reload(wait_until="networkidle")
                gpage.locator('.tab[data-tab="name"]').click()
                gpage.wait_for_timeout(2500)
                chips = gpage.locator(".nearby-chip").count()
                hidden = gpage.locator("#nearbyStores").evaluate("el => el.classList.contains('hidden')")
                results.append(
                    QAResult(
                        "UI-05",
                        "E",
                        "Nearby store chips",
                        "pass" if chips >= 1 and not hidden else "warn",
                        f"chips={chips}, hidden={hidden}",
                    )
                )
                geo_ctx.close()
            except Exception as exc:
                results.append(QAResult("UI-05", "E", "Nearby store chips", "fail", str(exc)[:120]))

            # UI-06 Wallet manage
            try:
                page.locator("#btnWalletSettings").click()
                page.locator("#view-manage").wait_for(state="visible")
                page.locator("#issuerQuery").fill("Chase")
                page.locator("#issuerSearchBtn").click()
                page.wait_for_timeout(2000)
                issuer_tiles = page.locator("#issuerResults .card-tile").count()
                results.append(
                    QAResult(
                        "UI-06",
                        "E",
                        "Wallet issuer search UI",
                        "pass" if issuer_tiles >= 1 else "fail",
                        f"{issuer_tiles} results",
                    )
                )
                page.locator("#manageBack").click()
            except Exception as exc:
                results.append(QAResult("UI-06", "E", "Wallet issuer search UI", "fail", str(exc)[:120]))

            # UI-07 Online recommend
            try:
                page.locator("#view-pay").wait_for(state="visible")
                page.locator('.tab[data-tab="url"]').click()
                page.fill("#merchantUrl", "https://www.chipotle.com/order")
                page.fill("#amount", "50")
                page.click("#go")
                page.wait_for_timeout(2500)
                if page.locator("#confirmModal").is_visible():
                    page.locator("#confirmGo").click()
                    page.wait_for_timeout(2500)
                err = page.locator("#error.show").inner_text() if page.locator("#error.show").count() else ""
                ok = page.locator("#result.show").count() > 0 and not err
                results.append(
                    QAResult(
                        "UI-07",
                        "E",
                        "Online URL recommend",
                        "pass" if ok else "fail",
                        err or page.locator("#bestName").inner_text()[:60],
                    )
                )
            except Exception as exc:
                results.append(QAResult("UI-07", "E", "Online URL recommend", "fail", str(exc)[:120]))

            # UI-08 In-store recommend
            try:
                page.locator('.tab[data-tab="name"]').click()
                page.fill("#merchantName", "Starbucks")
                page.click("#go")
                page.wait_for_timeout(2500)
                if page.locator("#confirmModal").is_visible():
                    page.locator("#confirmGo").click()
                    page.wait_for_timeout(2500)
                err = page.locator("#error.show").inner_text() if page.locator("#error.show").count() else ""
                ok = page.locator("#result.show").count() > 0 and not err
                results.append(
                    QAResult(
                        "UI-08",
                        "E",
                        "In-store recommend",
                        "pass" if ok else "fail",
                        err or page.locator("#bestName").inner_text()[:60],
                    )
                )
            except Exception as exc:
                results.append(QAResult("UI-08", "E", "In-store recommend", "fail", str(exc)[:120]))

            # UI-09 Savings history
            try:
                page.locator("#btnWalletSettings").click()
                hist_btn = page.locator("#btnWalletSavingsHistory")
                if hist_btn.is_visible():
                    hist_btn.click()
                    page.locator("#view-savings-history").wait_for(state="visible")
                    page.locator("#savingsHistoryBack").click()
                    results.append(QAResult("UI-09", "E", "Savings history navigation", "pass", "opened history"))
                else:
                    results.append(QAResult("UI-09", "E", "Savings history navigation", "warn", "no history yet"))
            except Exception as exc:
                results.append(QAResult("UI-09", "E", "Savings history navigation", "fail", str(exc)[:120]))

            # UI-10 Reset modal cancel
            try:
                page.locator("#btnWalletSettings").click()
                page.locator("#btnResetLocal").click()
                page.locator("#resetModal").wait_for(state="visible")
                page.locator("#resetCancel").click()
                results.append(QAResult("UI-10", "E", "Reset modal cancel", "pass", "modal dismissed"))
            except Exception as exc:
                results.append(QAResult("UI-10", "E", "Reset modal cancel", "fail", str(exc)[:120]))

            # UI-11 Home brand button
            try:
                page.locator("#btnHome").click()
                page.locator("#view-pay").wait_for(state="visible")
                results.append(QAResult("UI-11", "E", "Home brand shortcut", "pass", "back to pay"))
            except Exception as exc:
                results.append(QAResult("UI-11", "E", "Home brand shortcut", "fail", str(exc)[:120]))

            # UI-12 Change language from wallet
            try:
                page.locator("#btnWalletSettings").click()
                page.locator("#btnChangeLanguage").click()
                page.locator("#view-language").wait_for(state="visible")
                results.append(QAResult("UI-12", "E", "Change language from wallet", "pass", "language view"))
            except Exception as exc:
                results.append(QAResult("UI-12", "E", "Change language from wallet", "fail", str(exc)[:120]))

            browser.close()

        ctx.browser_available = True
        return results
