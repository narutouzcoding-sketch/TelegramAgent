"""Browser regression audit against the disposable QA panel only.

Start qa.ps1 -Browser first. Playwright and optional AXE_SOURCE are development tools.
Never points at a real Telegram panel or loads its credentials.
"""

import asyncio
import json
import os
import uuid
from pathlib import Path

from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8766"
OUT = Path(".qa/audit")


async def main():
    OUT.mkdir(parents=True, exist_ok=True)

    class Checks(list):
        def append(self, value):
            super().append(value)
            print("PASS: " + value, flush=True)

    checks = Checks()
    run = " " + uuid.uuid4().hex[:8]
    async with async_playwright() as playwright:
        executable = os.environ.get("PLAYWRIGHT_CHROMIUM_EXECUTABLE")
        browser = await playwright.chromium.launch(
            **({"executable_path": executable} if executable else {})
        )
        context = await browser.new_context(viewport={"width": 390, "height": 844})
        page = await context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(BASE + "/#plans")
        await page.locator("#login-form [name=password]").fill("Qa-Sinov-2026!")
        await page.locator("#login-form [type=submit]").click()
        await page.locator("#workspace").wait_for(state="visible")
        state = await (await context.request.get(BASE + "/api/state")).json()
        assert "SINOV AKKAUNTI" in state["agent"]["owner_name"], "Only disposable QA is allowed"
        assert await page.locator("#page-name").inner_text() == "Rejalar"
        checks.append("deep link restored after login/reload")

        async def idle():
            await page.wait_for_function("()=>activeOperations.size===0")

        async def go(name):
            await page.evaluate("(name)=>go(name)", name)

        async def field(selector, text):
            await page.locator(selector).fill(text)

        async def count_title(title):
            data = await (await context.request.get(BASE + "/api/state")).json()
            return sum(row["title"] == title for row in data["plans"])

        # Polling and remounting cannot re-enable a pending submission.
        entered = asyncio.Event()
        release = asyncio.Event()

        async def hold(route):
            entered.set()
            await asyncio.wait_for(release.wait(), 8)
            await route.continue_()

        await page.route("**/api/plan", hold)
        await field("#quick-plan-form [name=title]", ("QA pending submit" + run))
        await page.locator("#quick-plan-form [type=submit]").click()
        await asyncio.wait_for(entered.wait(), 10)
        await page.evaluate("refresh()")
        assert await page.locator("#quick-plan-form [type=submit]").is_disabled()
        await go("home")
        await go("plans")
        assert await page.locator("#quick-plan-form [type=submit]").is_disabled()
        release.set()
        await idle()
        await page.unroute("**/api/plan")
        assert await page.locator("#quick-plan-form [name=title]").input_value() == ""
        assert await count_title(("QA pending submit" + run)) == 1
        checks.append(
            "pending form stays disabled through polls and navigation; submitted draft cleared"
        )

        # Editing during submission must preserve the next draft.
        entered.clear()
        release.clear()
        await page.route("**/api/plan", hold)
        await field("#quick-plan-form [name=title]", ("QA submitted draft" + run))
        await page.locator("#quick-plan-form [type=submit]").click()
        await asyncio.wait_for(entered.wait(), 10)
        await field("#quick-plan-form [name=title]", ("QA next draft" + run))
        release.set()
        await idle()
        await page.unroute("**/api/plan")
        assert await page.locator("#quick-plan-form [name=title]").input_value() == (
            "QA next draft" + run
        )
        checks.append("new edits survive an older submission completing")

        # Lost response after commit: retry uses the same receipt, once completed.
        tickets = []

        async def lose_response(route):
            tickets.append(route.request.post_data_json["request_id"])
            await route.fetch()
            await route.abort("connectionreset")

        await page.route("**/api/plan", lose_response)
        await field("#quick-plan-form [name=title]", ("QA lost response" + run))
        await page.locator("#quick-plan-form [type=submit]").click()
        await idle()
        await page.unroute("**/api/plan")

        async def receipt_retry(route):
            tickets.append(route.request.post_data_json["request_id"])
            await route.continue_()

        await page.route("**/api/plan", receipt_retry)
        await page.locator("#quick-plan-form [type=submit]").click()
        await idle()
        await page.unroute("**/api/plan")
        assert len(tickets) == 2 and tickets[0] == tickets[1]
        assert await count_title(("QA lost response" + run)) == 1
        checks.append("network response loss and retry do not duplicate a plan")

        # A force refresh requested during an older poll is performed afterwards.
        await field("#quick-plan-form [name=title]", ("QA refresh collision" + run))
        entered.clear()
        release.clear()
        seen = False

        async def stale_state(route):
            nonlocal seen
            if seen:
                return await route.continue_()
            seen = True
            snapshot = await route.fetch()
            entered.set()
            await asyncio.wait_for(release.wait(), 8)
            await route.fulfill(response=snapshot)

        await page.route("**/api/state", stale_state)
        polling = asyncio.create_task(page.evaluate("refresh()"))
        await asyncio.wait_for(entered.wait(), 10)
        await page.locator("#quick-plan-form [type=submit]").click()
        await page.wait_for_function("()=>refreshFlight?.again===true")
        release.set()
        await polling
        await idle()
        await page.unroute("**/api/state")
        assert ("QA refresh collision" + run) in await page.locator(
            "#ref-plan-results"
        ).inner_text()
        checks.append("mutation refresh cannot be swallowed by an older poll")

        # A pending chat remains marked pending after navigation.
        await go("chat")
        await field("#chat-form [name=text]", ("QA pending conversation" + run))
        await page.locator("#chat-form [type=submit]").click()
        await go("contacts")
        await go("chat")
        assert await page.locator("#chat-form [type=submit]").is_disabled()
        await idle()
        assert "SINOV: xabaringiz qabul qilindi" in await page.locator("#chat-thread").inner_text()
        checks.append("chat pending state survives tab changes")

        # Contact matching, keyboard picker and text-mode controls.
        await go("contacts")
        await field("#contact-search", "sevinch kursdoshga")
        assert "qidiruvda 1 ta" in await page.locator("#contact-match-count").inner_text()
        await page.locator("[data-contact-compose][data-mode=text]").click()
        assert not await page.locator(".call-advanced").first.is_visible()
        assert "xabar yuboramiz" in await page.locator("#call-form > label").first.inner_text()
        await field("#call-form [name=target]", "QA Sinov")
        await page.locator("#call-form [name=target]").press("ArrowUp")
        last = await page.locator("#recipient-options [role=option]").last.get_attribute("id")
        assert (
            await page.locator("#call-form [name=target]").get_attribute("aria-activedescendant")
            == last
        )
        await page.locator("#call-form [name=target]").press("Enter")
        assert await page.locator("#call-form [name=contact_id]").input_value()
        assert await page.evaluate(
            "AgentContacts.matches({name:'Hisobot 2026',reference:''},'2026')"
        )
        assert "2030" in await page.evaluate("dateTime('2030-01-15T10:00:00Z')")
        checks.append(
            "contact suffix/Unicode, numeric text, keyboard selection, text labels and future year"
        )

        # Lost response for an already-finished synthetic text task cannot resend it.
        await field("#call-form [name=message]", ("QA simulated only, never delivered" + run))

        async def lose_call(route):
            await route.fetch()
            await route.abort("connectionreset")

        await page.route("**/api/call", lose_call)
        await page.locator("#call-form [type=submit]").click()
        await idle()
        await page.unroute("**/api/call")
        await page.locator("#call-form [type=submit]").click()
        await idle()
        data = await (await context.request.get(BASE + "/api/state")).json()
        assert (
            sum(
                row["message"] == ("QA simulated only, never delivered" + run)
                for row in data["calls"]
            )
            == 1
        )
        checks.append("completed simulated task retry does not create another task")

        # A connected transport is not permission to send during a Telegram wait.
        async def waiting_telegram(route):
            response = await route.fetch()
            data = await response.json()
            data["agent"]["telegram_paused"] = True
            data["agent"]["telegram_pause_until"] = "2030-01-15T10:00:00Z"
            await route.fulfill(response=response, json=data)

        await page.route("**/api/state", waiting_telegram)
        await page.evaluate("refresh(true)")
        assert await page.locator("#agent-alert").is_visible()
        assert await page.locator("#call-form [type=submit]").is_disabled()
        await page.set_viewport_size({"width": 320, "height": 800})
        assert await page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        await go("plans")
        assert await page.locator("#quick-plan-form [type=submit]").is_enabled()
        await page.unroute("**/api/state")
        await page.evaluate("refresh(true)")
        checks.append("Telegram wait is visible, sending is blocked, local plans remain available")

        # Logging out while a state response is in flight cannot resurrect private UI.
        entered.clear()
        release.clear()

        async def late_state(route):
            snapshot = await route.fetch()
            entered.set()
            await asyncio.wait_for(release.wait(), 8)
            await route.fulfill(response=snapshot)

        await page.route("**/api/state", late_state)
        polling = asyncio.create_task(page.evaluate("refresh()"))
        await asyncio.wait_for(entered.wait(), 10)
        await page.evaluate("document.querySelector('#logout').click()")
        await page.locator("#login").wait_for(state="visible")
        release.set()
        await polling
        await page.unroute("**/api/state")
        assert await page.locator("#workspace").is_hidden()
        assert await page.locator("#main").inner_text() == ""
        assert await page.evaluate("state===null")
        checks.append("late state response after logout cannot restore private data")
        assert not errors, errors

        await field("#login-form [name=password]", "Qa-Sinov-2026!")
        await page.locator("#login-form [type=submit]").click()
        await page.locator("#workspace").wait_for(state="visible")
        await idle()
        for width, height in [(320, 800), (390, 844), (768, 900), (1440, 1000), (844, 390)]:
            await page.set_viewport_size({"width": width, "height": height})
            for theme in ["light", "dark"]:
                if await page.locator("html").get_attribute("data-theme") != theme:
                    await page.locator("#workspace [data-theme-toggle]").click()
                for name in [
                    "home",
                    "chat",
                    "calls",
                    "plans",
                    "reminders",
                    "contacts",
                    "recordings",
                    "library",
                ]:
                    await go(name)
                    assert await page.evaluate(
                        "document.documentElement.scrollWidth<=innerWidth"
                    ), (width, height, theme, name)
                    if width == 390:
                        await page.screenshot(path=str(OUT / f"{name}-{theme}.png"), full_page=True)
        checks.append("8 pages × 5 viewports × 2 themes without horizontal overflow")
        assert not errors, errors
        await context.close()

        axe_path = os.environ.get("AXE_SOURCE")
        violations = {}
        if axe_path:
            # Test instrumentation is confined to a second disposable context;
            # production CSP is unchanged and the functional tests above used it.
            context = await browser.new_context(
                viewport={"width": 390, "height": 844}, bypass_csp=True
            )
            await context.request.post(BASE + "/api/login", data={"password": "Qa-Sinov-2026!"})
            page = await context.new_page()
            await page.goto(BASE)
            await page.locator("#workspace").wait_for(state="visible")
            await page.add_script_tag(path=axe_path)
            for theme in ["light", "dark"]:
                if await page.locator("html").get_attribute("data-theme") != theme:
                    await page.locator("#workspace [data-theme-toggle]").click()
                for name in [
                    "home",
                    "chat",
                    "calls",
                    "plans",
                    "reminders",
                    "contacts",
                    "recordings",
                    "library",
                ]:
                    await page.evaluate("(name)=>go(name)", name)
                    violations[theme + "-" + name] = await page.evaluate(
                        "async()=>{const r=await axe.run(document.querySelector('#workspace'),{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21aa']}});return r.violations.map(v=>({id:v.id,nodes:v.nodes.map(n=>({target:n.target,summary:n.failureSummary}))}));}"
                    )
            await context.close()
        report = {
            "checks": checks,
            "js_errors": errors,
            "accessibility": violations,
            "real_telegram_or_ai": False,
        }
        (OUT / "browser-report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "passed": checks,
                    "accessibility_violations": {
                        k: [v["id"] for v in rows] for k, rows in violations.items() if rows
                    },
                    "js_errors": errors,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        assert not any(violations.values()), "Accessibility findings: .qa/audit/browser-report.json"
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
