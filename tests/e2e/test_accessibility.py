# Kilo Tracker - a small weight-tracking web app.
# Copyright (C) 2026 Ramón de Vries <ramon@11tools.com>
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version. See the LICENSE file for the full text.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.

"""Every page, and the dashboard with its dialogs, editor and menus open, checked by axe-core.

axe (https://github.com/dequelabs/axe-core, through axe-playwright-python) finds the problems a
machine can: missing names and labels, contrast, heading order, ARIA misuse. Each check runs in
the light and the dark theme where a page has one (signed-out pages are always light). It cannot
judge whether a text makes sense when read aloud, so a pass here is a floor, not a proof. Run
with `pytest -m e2e` (see requirements-e2e.txt).
"""

from datetime import date

import pytest

from tests.e2e.test_dashboard import HISTORY

axe_playwright = pytest.importorskip("axe_playwright_python.sync_playwright")

pytestmark = pytest.mark.e2e
both_themes = pytest.mark.parametrize("dark", [False, True], ids=["light", "dark"])

AXE = axe_playwright.Axe()


def assert_accessible(page):
    """Fail with axe's findings, one line per rule and element, so the report says what to fix."""
    violations = AXE.run(page).response["violations"]
    found = [f"{v['id']} ({v['impact']}): {v['help']} at {node['target']}" for v in violations for node in v["nodes"]]
    assert not found, f"{page.url}\n" + "\n".join(found)


@pytest.fixture
def signed_in(live_server, context, page):
    """Sign in as a user with a height, a shared chart and ten days of weights (none today, so the
    "today" prompt opens on the dashboard); returns a function that opens a path."""

    def open_(path, dark):
        user_id = live_server.add_user(weights=HISTORY, dark_mode=dark, height_cm=180,
                                       public_enabled=True, public_id="mine", public_show_stats=True)
        live_server.sign_in(context, user_id)
        page.goto(live_server.url + path)

    return open_


def test_the_sign_in_page(live_server, page):
    page.goto(live_server.url + "/")
    assert_accessible(page)


def test_the_about_page(live_server, page):
    page.goto(live_server.url + "/about")
    assert_accessible(page)


@pytest.mark.expected_http_errors  # the page is a 404
def test_the_missing_public_chart_page(live_server, page):
    page.goto(live_server.url + "/public/nope")
    assert_accessible(page)


@both_themes
def test_the_dashboard_with_the_today_prompt(signed_in, page, dark):
    signed_in("/", dark)
    page.locator("#today-prompt").wait_for()
    assert_accessible(page)


@both_themes
def test_the_dashboard_with_the_unusual_value_question(signed_in, page, dark):
    signed_in("/", dark)
    page.fill("#today-prompt-weight", "95")
    page.click("#today-prompt-ok")
    page.locator("#outlier-prompt").wait_for()
    assert_accessible(page)


@both_themes
def test_the_dashboard_with_the_note_editor_and_emoji_panel(signed_in, page, dark):
    signed_in("/", dark)
    page.click("#today-prompt-skip")
    row = page.locator(f'.day-row[data-date="{date.today().isoformat()}"]')
    row.locator(".note-btn").click()
    row.locator(".note-emoji-btn").click()
    page.locator("#emoji-panel").wait_for()
    assert_accessible(page)


@both_themes
def test_the_dashboard_with_the_account_menu(signed_in, page, dark):
    signed_in("/", dark)
    page.click("#today-prompt-skip")
    page.click("#account-trigger")
    assert_accessible(page)


@both_themes
def test_the_settings_page(signed_in, page, dark):
    signed_in("/settings", dark)
    assert_accessible(page)


@both_themes
def test_the_remove_my_data_page(signed_in, page, dark):
    signed_in("/settings/remove", dark)
    assert_accessible(page)


@both_themes
@pytest.mark.parametrize("show_weight", [True, False], ids=["weights", "no-weights"])
def test_the_public_chart(live_server, page, dark, show_weight):
    live_server.add_user(weights=HISTORY, public_enabled=True, public_id="mine", public_show_stats=show_weight,
                         public_show_weight=show_weight, height_cm=180)
    page.goto(f"{live_server.url}/public/mine?theme={'dark' if dark else 'light'}")
    assert_accessible(page)

