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

"""The web app manifest (static/manifest.json), so Kilo installs on a phone's home screen.

Whether Chromium really finds it installable is checked by the browser test
`test_chromium_can_install_kilo_as_an_app`; these tests keep the pages, the manifest and the icon
files in step.
"""

import json
import re
import struct

import pytest

from app import db
from app.models import User
from tests.conftest import ROOT, signup_and_verify

LINK = re.compile(r'<link rel="(manifest|apple-touch-icon)" href="([^"]+)">')


def png_size(data):
    """(width, height) from a PNG's header."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def links(html):
    return dict(LINK.findall(html))


@pytest.mark.parametrize("path", ["/", "/about"])
def test_signed_out_pages_link_the_manifest_and_the_apple_icon(client, path):
    found = links(client.get(path).data.decode())
    assert set(found) == {"manifest", "apple-touch-icon"}
    for href in found.values():
        assert client.get(href).status_code == 200


@pytest.mark.parametrize("path", ["/", "/settings", "/about"])
def test_signed_in_pages_link_the_manifest_too(client, path):
    signup_and_verify(client, "user@example.com")
    assert set(links(client.get(path).data.decode())) == {"manifest", "apple-touch-icon"}


def test_the_public_chart_is_not_offered_as_the_app(client):
    """It is the owner's page, often inside someone else's site: installing it would install
    Kilo's sign-in page instead."""
    signup_and_verify(client, "owner@example.com")
    owner = User.query.one()
    owner.public_id, owner.public_enabled = "mine", True
    db.session.commit()
    html = client.get("/public/mine").data.decode()
    assert links(html) == {}


def test_the_manifest_opens_the_dashboard_as_an_app_with_its_icons(client):
    response = client.get(links(client.get("/").data.decode())["manifest"])
    assert response.mimetype == "application/json"
    manifest = json.loads(response.data)
    assert manifest["name"] == "Kilo Tracker"
    assert manifest["start_url"] == "/" and manifest["scope"] == "/"
    assert manifest["display"] == "standalone"
    sizes = {}
    for icon in manifest["icons"]:
        assert icon["type"] == "image/png"
        # Icon addresses are relative to the manifest, so in static/.
        data = client.get("/static/" + icon["src"]).data
        width, height = png_size(data)
        assert icon["sizes"] == f"{width}x{height}"
        sizes.setdefault(icon["purpose"], set()).add(width)
    # What Chrome asks for: 192 and 512 pixels, and a maskable one Android may crop to a circle.
    assert {192, 512} <= sizes["any"] and 512 in sizes["maskable"]


def test_the_apple_icon_is_the_size_ios_uses(client):
    href = links(client.get("/").data.decode())["apple-touch-icon"]
    assert png_size(client.get(href).data) == (180, 180)


def test_the_browser_bar_takes_the_header_colour_of_the_theme(client):
    signup_and_verify(client, "user@example.com")
    theme_color = re.compile(r'<meta name="theme-color" id="theme-color" content="([^"]+)"')
    assert theme_color.search(client.get("/").data.decode())[1] == "#ffffff"
    User.query.one().dark_mode = True
    db.session.commit()
    assert theme_color.search(client.get("/").data.decode())[1] == "#1e2426"


def test_those_colours_are_the_headers_in_style_css():
    """base.html and manifest.json repeat the header colour (--surface); a new look must change them too."""
    css = (ROOT / "app/static/style.css").read_text()
    light = re.search(r":root \{[^}]*--surface: (#\w+);", css)[1]
    dark = re.search(r'html\[data-theme="dark"\] \{[^}]*--surface: (#\w+);', css)[1]
    assert (light, dark) == ("#ffffff", "#1e2426")
    manifest = json.loads((ROOT / "app/static/manifest.json").read_text())
    assert manifest["theme_color"] == light
