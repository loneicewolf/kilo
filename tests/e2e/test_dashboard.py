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

"""The dashboard in a real browser: the page script's flows that pytest alone cannot run.

Saving a day, the "is this right?" question for an unusual weight, Undo after clearing, the
note editor, the "today" prompt, the range buttons, dark mode and the session-expired dialog.
Run with `pytest -m e2e` (see requirements-e2e.txt).
"""

from datetime import date, timedelta

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e

# Ten days of weights up to yesterday, about 80 kg; today is left to each test.
HISTORY = {days_ago: 80.0 + (days_ago % 3) / 10 for days_ago in range(1, 11)}


def day(days_ago=0):
    return (date.today() - timedelta(days=days_ago)).isoformat()


@pytest.fixture
def dashboard(live_server, context, page):
    """Open the dashboard signed in; returns (page, user id). Today already has an entry, so
    the "today" prompt stays away unless a test wants it."""

    def open_(weights=None, notes=None, **columns):
        user_id = live_server.add_user(weights={0: 80.2, **HISTORY} if weights is None else weights,
                                       notes=notes, **columns)
        live_server.sign_in(context, user_id)
        page.goto(live_server.url + "/")
        return user_id

    return open_


def row(page, days_ago=0):
    return page.locator(f'.day-row[data-date="{day(days_ago)}"]')


def type_weight(page, text, days_ago=0):
    """Type into a day's weight field and leave it, as a person does (change fires on leaving)."""
    field = row(page, days_ago).locator(".day-weight")
    field.fill(text)
    field.press("Tab")


def test_a_weight_typed_in_the_log_is_saved(dashboard, live_server, page):
    user_id = dashboard()
    type_weight(page, "80,4")  # a comma is fine in every language
    expect(row(page).locator(".day-status")).to_have_text("Saved")
    assert live_server.entry(user_id) == (80.4, None)
    expect(page.locator("#stat-current")).not_to_be_empty()
    assert page.evaluate("chart.data.datasets[0].data.at(-1)") == 80.4  # the chart took the save's series
    page.reload()
    expect(row(page).locator(".day-weight")).to_have_value("80.4")


def test_an_unusual_weight_is_saved_only_after_save_anyway(dashboard, live_server, page):
    user_id = dashboard()
    type_weight(page, "95")
    expect(page.locator("#outlier-prompt")).to_be_visible()
    expect(page.locator("#outlier-message")).to_contain_text("95")
    assert live_server.entry(user_id) == (80.2, None)  # nothing saved yet
    page.click("#outlier-confirm")
    expect(page.locator("#outlier-prompt")).to_be_hidden()
    expect(row(page).locator(".day-status")).to_have_text("Saved")
    assert live_server.entry(user_id) == (95.0, None)


def test_correct_it_goes_back_to_the_field_and_saves_nothing(dashboard, live_server, page):
    user_id = dashboard()
    type_weight(page, "95")
    page.click("#outlier-correct")
    expect(page.locator("#outlier-prompt")).to_be_hidden()
    expect(row(page).locator(".day-weight")).to_be_focused()
    assert live_server.entry(user_id) == (80.2, None)


def test_a_cleared_weight_comes_back_with_its_note_after_undo(dashboard, live_server, page):
    user_id = dashboard(notes={0: "after the party"})
    type_weight(page, "")
    expect(page.locator("#undo-toast")).to_be_visible()
    expect(page.locator("#undo-message")).to_have_text(f"Weight of {shown_date(0)} removed.")
    assert live_server.entry(user_id) is None
    page.click("#undo-btn")
    expect(row(page).locator(".day-status")).to_have_text("Saved")
    expect(page.locator("#undo-toast")).to_be_hidden()
    assert live_server.entry(user_id) == (80.2, "after the party")
    page.reload()
    expect(row(page).locator(".day-weight")).to_have_value("80.2")
    expect(row(page).locator(".note-btn")).to_have_class("note-btn has-note")


def test_a_note_is_written_and_saved_in_the_note_editor(dashboard, live_server, page):
    user_id = dashboard()
    today = row(page)
    today.locator(".note-btn").click()
    expect(today.locator(".note-popover")).to_be_visible()
    today.locator(".note-textarea").fill("long walk 🚶")
    today.locator(".note-save").click()
    expect(today.locator(".note-popover")).to_be_hidden()
    expect(today.locator(".day-status")).to_have_text("Saved")
    assert live_server.entry(user_id) == (80.2, "long walk 🚶")


def test_escape_closes_the_note_editor_without_saving(dashboard, live_server, page):
    user_id = dashboard()
    today = row(page)
    today.locator(".note-btn").click()
    today.locator(".note-textarea").fill("not this")
    today.locator(".note-textarea").press("Escape")
    expect(today.locator(".note-popover")).to_be_hidden()
    assert live_server.entry(user_id) == (80.2, None)


def test_the_today_prompt_saves_todays_weight(dashboard, live_server, page):
    user_id = dashboard(weights=HISTORY)  # nothing today
    expect(page.locator("#today-prompt")).to_be_visible()
    page.fill("#today-prompt-weight", "80,1")
    page.click("#today-prompt-ok")
    expect(page.locator("#today-prompt")).to_be_hidden()
    expect(row(page).locator(".day-weight")).to_have_value("80.1")
    assert live_server.entry(user_id) == (80.1, None)


def test_a_skipped_today_prompt_stays_away_for_the_day(dashboard, page):
    dashboard(weights=HISTORY)
    page.click("#today-prompt-skip")
    expect(page.locator("#today-prompt")).to_be_hidden()
    page.reload()
    page.wait_for_load_state("load")
    expect(page.locator("#today-prompt")).to_be_hidden()


def test_the_today_prompt_is_a_named_modal_dialog_that_keeps_the_focus(dashboard, page):
    dashboard(weights=HISTORY)  # nothing today
    dialog = page.get_by_role("dialog", name="Log today's weight?")
    expect(dialog).to_be_visible()
    assert page.evaluate("document.getElementById('today-prompt').matches(':modal')")
    expect(page.locator("#today-prompt-weight")).to_be_focused()
    # Tab goes round the dialog (and at most out to the browser), never into the page behind it.
    for _ in range(8):
        page.keyboard.press("Tab")
        assert page.evaluate("""() => {
            const el = document.activeElement;
            return el === document.body || el.closest('#today-prompt') !== null;
        }""")


def test_escape_on_the_today_prompt_counts_as_skip(dashboard, page):
    dashboard(weights=HISTORY)
    expect(page.locator("#today-prompt")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("#today-prompt")).to_be_hidden()
    page.reload()
    page.wait_for_load_state("load")
    expect(page.locator("#today-prompt")).to_be_hidden()


def test_escape_closes_the_unusual_value_question_without_saving(dashboard, live_server, page):
    user_id = dashboard()
    type_weight(page, "95")
    expect(page.get_by_role("dialog", name="Unusual value")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("#outlier-prompt")).to_be_hidden()
    assert live_server.entry(user_id) == (80.2, None)
    # Focus is back in the row that asked, not lost at the top of the page.
    assert page.evaluate("document.activeElement.closest('.day-row')?.dataset.date") == day(0)


def test_a_range_button_changes_the_chart_and_is_remembered(dashboard, live_server, page):
    user_id = dashboard(weights=dict.fromkeys(range(40), 80.0))
    with page.expect_response(lambda response: response.url.endswith("/chart-range")) as saved:
        page.click('.range-btn[data-range="1m"]')
    assert saved.value.ok
    expect(page.locator('.range-btn[data-range="1m"]')).to_have_class("range-btn active")
    expect(page.locator('.range-btn[data-range="1m"]')).to_have_attribute("aria-pressed", "true")
    # A screen reader says what is on the button, then what it means.
    expect(page.locator('.range-btn[data-range="1m"]')).to_have_accessible_name("1M")
    expect(page.locator('.range-btn[data-range="1m"]')).to_have_accessible_description("1 month")
    expect(page.locator('.range-btn[data-range="all"]')).to_have_attribute("aria-pressed", "false")
    assert page.evaluate("chart.data.labels.length") == 31  # today minus 30 days .. today
    page.reload()
    expect(page.locator('.range-btn[data-range="1m"]')).to_have_class("range-btn active")
    assert live_server.user(user_id).chart_range == "1m"


def shown_date(days_ago, month="%B"):
    """A date in English as the page gives it to a screen reader, "October 27, 2026" (Intl's long
    style), or with month="%b" as it shows it on screen, "Oct 27, 2026"."""
    d = date.today() - timedelta(days=days_ago)
    return f"{d:{month}} {d.day}, {d.year}"


def test_older_days_loaded_while_scrolling_are_named_for_screen_readers(dashboard, page):
    dashboard(weights=dict.fromkeys(range(40), 80.0))  # more than one page of the log (30 days)
    page.locator(".entries").evaluate("panel => panel.scrollTo(0, panel.scrollHeight)")
    older = row(page, 35)  # added by the script, from the empty row template
    expect(older).to_be_attached()
    expect(older.locator(".day-date")).to_have_text(shown_date(35, "%b"))  # short on screen
    expect(older.locator(".day-weight")).to_have_attribute("aria-label", f"Weight on {shown_date(35)}")
    expect(older.locator(".note-btn")).to_have_attribute("aria-label", f"Note for {shown_date(35)}")


def test_a_stat_box_reached_with_the_keyboard_shows_the_focus_outline(dashboard, page):
    dashboard(weights=dict.fromkeys(range(40), 80.0))
    box = page.locator(".stat-card-link").first
    box.focus()
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Tab")  # focus by keyboard, so :focus-visible applies
    expect(box).to_be_focused()
    assert box.evaluate("el => getComputedStyle(el).outlineStyle") != "none"


def test_the_skip_link_is_the_first_tab_stop_and_jumps_to_the_daily_log(dashboard, page):
    dashboard()
    page.keyboard.press("Tab")
    link = page.locator(".skip-link")
    expect(link).to_be_focused()
    expect(link).to_have_text("Skip to the daily log")
    assert link.evaluate("el => el.getBoundingClientRect().top") >= 0  # on screen once focused
    page.keyboard.press("Enter")
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.closest('#daily-log') !== null")


def test_less_motion_when_the_system_asks_for_it(dashboard, page):
    dashboard(weights=dict.fromkeys(range(40), 80.0))
    duration = "() => getComputedStyle(document.querySelector('.range-btn')).transitionDuration"
    assert page.evaluate(duration) != "0s"
    page.emulate_media(reduced_motion="reduce")
    assert page.evaluate(duration) == "0s"
    panel = page.locator(".entries")
    panel.evaluate("panel => panel.scrollTo(0, panel.scrollHeight)")
    expect(row(page, 35)).to_be_attached()
    page.click("#scroll-top-btn")
    assert panel.evaluate("panel => panel.scrollTop") == 0  # at once, not a smooth scroll


def test_the_emoji_panel_is_one_tab_stop_with_arrow_keys_inside(dashboard, live_server, page):
    dashboard()
    today = row(page)
    today.locator(".note-btn").click()
    today.locator(".note-emoji-btn").click()
    expect(page.locator("#emoji-panel")).to_be_visible()
    textarea = today.locator(".note-textarea")
    expect(textarea).to_be_focused()
    emoji = page.locator("#emoji-grid .emoji-btn")
    page.keyboard.press("Tab")
    expect(emoji.nth(0)).to_be_focused()
    page.keyboard.press("Tab")  # one Tab past all 60 emoji, on to the editor's own buttons
    expect(today.locator(".note-emoji-btn")).to_be_focused()
    page.keyboard.press("Shift+Tab")
    expect(emoji.nth(0)).to_be_focused()
    page.keyboard.press("ArrowRight")
    expect(emoji.nth(1)).to_be_focused()
    columns = emoji.evaluate_all("""buttons => buttons.filter(
        b => b.getBoundingClientRect().top === buttons[0].getBoundingClientRect().top).length""")
    page.keyboard.press("ArrowDown")
    expect(emoji.nth(1 + columns)).to_be_focused()
    page.keyboard.press("End")
    expect(emoji.last).to_be_focused()
    page.keyboard.press("ArrowLeft")
    expect(emoji.nth(emoji.count() - 2)).to_be_focused()
    page.keyboard.press("Enter")
    expect(textarea).to_have_value(emoji.nth(emoji.count() - 2).inner_text())
    expect(textarea).to_be_focused()  # back in the note, to type on
    page.keyboard.press("Tab")
    expect(emoji.nth(emoji.count() - 2)).to_be_focused()  # the panel remembers where it was
    page.keyboard.press("Tab")  # out of the panel in one step, on to the editor's own buttons
    expect(today.locator(".note-emoji-btn")).to_be_focused()
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Home")
    expect(emoji.nth(0)).to_be_focused()
    page.keyboard.press("Escape")  # closes the panel, keeps the editor and the text
    expect(page.locator("#emoji-panel")).to_be_hidden()
    expect(today.locator(".note-popover")).to_be_visible()
    expect(textarea).to_be_focused()




def test_the_chart_is_described_in_words_for_screen_readers(dashboard, page):
    dashboard()  # 80.2 today, HISTORY before: 80.1, 80.2, 80.0, ... back to 80.1 ten days ago
    chart = page.get_by_role("img", name="Weight chart")
    expect(chart).to_have_accessible_description(
        f"All weigh-ins: from 80.1 kg on {shown_date(10)} to 80.2 kg on {shown_date(0)}. "
        "Lowest 80.0 kg, highest 80.2 kg, average 80.1 kg.")
    page.click('.range-btn[data-range="1w"]')
    expect(chart).to_have_accessible_description(
        f"1 week: from 80.1 kg on {shown_date(7)} to 80.2 kg on {shown_date(0)}. "
        "Lowest 80.0 kg, highest 80.2 kg, average 80.1 kg.")


def test_the_description_follows_a_save_and_says_when_a_period_is_empty(dashboard, page):
    dashboard(weights={20: 80.0, 21: 81.0}, chart_range="1w")
    chart = page.get_by_role("img", name="Weight chart")
    expect(chart).to_have_accessible_description("1 week: no weigh-ins in this period.")
    page.click("#today-prompt-skip")
    type_weight(page, "79,5")
    expect(row(page).locator(".day-status")).to_have_text("Saved")
    expect(chart).to_have_accessible_description(
        f"1 week: from 79.5 kg on {shown_date(0)} to 79.5 kg on {shown_date(0)}. "
        "Lowest 79.5 kg, highest 79.5 kg, average 79.5 kg.")


def test_all_reaches_today_even_when_the_last_entry_is_older(dashboard, page):
    dashboard(weights=dict.fromkeys(range(3, 20), 80.0))  # nothing for the last 3 days
    labels = page.evaluate("chart.data.labels")
    assert labels[0] == day(19) and labels[-1] == day(0) and len(labels) == 20
    assert page.evaluate("chart.data.datasets[0].data.slice(-3)") == [None, None, None]


def test_a_long_history_is_thinned_out_and_its_average_stays_exact(dashboard, page):
    # 1,500 days alternating 80 and 82 kg: more than MAX_PLOT_POINTS, so the chart averages
    # buckets of days; the dotted overall average is still that of every single day.
    dashboard(weights={days_ago: 80.0 + 2 * (days_ago % 2) for days_ago in range(1500)})
    assert page.evaluate("chart.data.labels.length") == 1000
    assert page.evaluate("chart.data.datasets[2].data[0]") == pytest.approx(81.0, abs=0.01)
    assert page.evaluate("chart.data.datasets[1].data.length") == 0  # no moving average on All


def test_dark_mode_switches_at_once_and_is_remembered(dashboard, live_server, page):
    user_id = dashboard()
    expect(page.locator("html")).to_have_attribute("data-theme", "light")
    expect(page.locator('meta[name="theme-color"]')).to_have_attribute("content", "#ffffff")
    page.click("#account-trigger")
    with page.expect_response(lambda response: response.url.endswith("/settings/dark-mode")) as saved:
        page.locator("#account-dropdown .toggle-switch").click()
    assert saved.value.ok
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    # The phone's browser bar (or the installed app's title bar) takes the dark header colour too.
    expect(page.locator('meta[name="theme-color"]')).to_have_attribute("content", "#1e2426")
    page.reload()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    expect(page.locator('meta[name="theme-color"]')).to_have_attribute("content", "#1e2426")
    assert live_server.user(user_id).dark_mode is True


def _contrast(page, selector):
    """WCAG contrast ratio of an element's text against its own background colour."""
    return page.locator(selector).first.evaluate("""el => {
        const rgb = (value) => value.match(/[\\d.]+/g).slice(0, 3).map(Number);
        const luminance = (value) => {
            const [r, g, b] = rgb(value).map((c) => {
                c /= 255;
                return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
            });
            return 0.2126 * r + 0.7152 * g + 0.0722 * b;
        };
        const style = getComputedStyle(el);
        const [hi, lo] = [luminance(style.color), luminance(style.backgroundColor)].sort((a, b) => b - a);
        return (hi + 0.05) / (lo + 0.05);
    }""")


@pytest.mark.parametrize("dark", [False, True])
def test_text_on_the_green_and_red_buttons_is_readable_in_both_themes(dashboard, live_server, page, dark):
    dashboard(dark_mode=dark)
    assert _contrast(page, ".range-btn.active") >= 4.5
    page.goto(live_server.url + "/settings")
    assert _contrast(page, "button.form-action") >= 4.5  # Save
    assert _contrast(page, ".button-danger") >= 4.5
    assert _contrast(page, ".button-warning") >= 4.5


@pytest.mark.expected_http_errors  # the refused save is a 400
def test_an_expired_session_shows_the_dialog_instead_of_saving(dashboard, live_server, context, page):
    user_id = dashboard()
    context.clear_cookies()  # as when the session has run out
    type_weight(page, "79,9")
    expect(page.get_by_role("alertdialog", name="Session expired")).to_be_visible()
    expect(row(page).locator(".day-status")).to_have_text("")
    page.keyboard.press("Escape")  # nothing can be saved until a reload, so it stays
    expect(page.locator("#session-expired-prompt")).to_be_visible()
    expect(page.locator("#session-expired-reload")).to_be_focused()
    assert live_server.entry(user_id) == (80.2, None)


def test_chromium_can_install_kilo_as_an_app(dashboard, context, page):
    """Chromium's own check: the manifest loads, and its name, start page and icons make Kilo
    installable ("Add to Home Screen" opens it as an app, not as a bookmark)."""
    dashboard()
    cdp = context.new_cdp_session(page)
    manifest = cdp.send("Page.getAppManifest")
    assert manifest["errors"] == []
    assert manifest["url"].startswith(page.url.rstrip("/") + "/static/manifest.json")
    assert cdp.send("Page.getInstallabilityErrors")["installabilityErrors"] == []
