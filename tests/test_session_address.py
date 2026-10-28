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

"""The email address in the session cookie is encrypted (app/session_address.py).

The cookie is decoded here the way anyone holding it could (it is signed, not encrypted), and
must not show the address; the pages that need the address must still get it.
"""

import json

from cryptography.fernet import Fernet

from app import mail
from app.models import User
from tests.conftest import code_from, flashes, session_address_of, signup_and_verify

EMAIL = "secret.person@example.com"


def cookie_contents(client):
    """The session cookie as anyone who has it can read it: no key needed."""
    value = client.get_cookie("session").value
    serializer = client.application.session_interface.get_signing_serializer(client.application)
    return json.dumps(serializer.loads(value))


def test_a_signed_in_cookie_does_not_show_the_address(client):
    signup_and_verify(client, EMAIL)
    page = client.get("/").get_data(as_text=True)  # also takes the flashes out of the cookie
    assert EMAIL in page  # the header still shows it
    contents = cookie_contents(client)
    assert "secret.person" not in contents and "example.com" not in contents
    assert session_address_of(client) == EMAIL


def test_a_sign_in_waiting_for_its_code_does_not_show_the_address_either(client):
    with mail.record_messages() as outbox:
        client.post("/signup", data={"email": EMAIL})
    client.get("/verify")  # shows the "code sent" flash, which names the address once
    assert "example.com" not in cookie_contents(client)
    client.post("/verify", data={"code": code_from(outbox)})
    assert session_address_of(client) == EMAIL


def test_the_removal_code_still_goes_to_the_address(client):
    signup_and_verify(client, EMAIL)
    client.get("/settings/export")
    with mail.record_messages() as outbox:
        client.post("/settings/remove/send-code")
    assert [message.recipients for message in outbox] == [[EMAIL]]


def test_the_export_is_still_named_after_the_address(client):
    signup_and_verify(client, EMAIL)
    response = client.get("/settings/export")
    assert EMAIL in response.headers["Content-Disposition"]


def test_a_readable_address_from_before_is_encrypted_at_the_next_visit(client):
    signup_and_verify(client, EMAIL)
    user_id = User.query.one().id
    with client.session_transaction() as sess:  # a cookie from before the encryption
        del sess["address"]
        sess["email"] = EMAIL
    assert EMAIL in client.get("/").get_data(as_text=True)
    with client.session_transaction() as sess:
        assert "email" not in sess and sess["user_id"] == user_id
    assert "example.com" not in cookie_contents(client)
    assert session_address_of(client) == EMAIL


def test_an_address_that_does_not_decrypt_is_simply_missing(client):
    """Encrypted with another key (another SECRET_KEY) or damaged: no address, no error."""
    signup_and_verify(client, EMAIL)
    client.get("/")  # take the flashes, which name the address, out of the session
    for token in (Fernet(Fernet.generate_key()).encrypt(EMAIL.encode()).decode(), "not-a-token"):
        with client.session_transaction() as sess:
            sess["address"] = token
        response = client.get("/")
        assert response.status_code == 200
        page = response.get_data(as_text=True)
        assert EMAIL not in page and "Signed in" in page


def test_the_code_sent_notice_names_the_address_without_carrying_it_in_the_cookie(client):
    """A flash waits in the cookie until the next page; the notice is only made on that page."""
    client.post("/signup", data={"email": EMAIL})
    assert "example.com" not in cookie_contents(client)
    assert flashes(client.get("/verify")) == [f"We sent a verification code to {EMAIL}."]
    assert flashes(client.get("/verify")) == []  # once

    client.post("/verify/resend")
    assert "example.com" not in cookie_contents(client)
    assert flashes(client.get("/verify")) == [f"We sent a new code to {EMAIL}."]


def test_the_removal_code_notice_too(client):
    signup_and_verify(client, EMAIL)
    client.get("/")  # shows "Email verified"
    client.get("/settings/export")
    client.post("/settings/remove/send-code")
    assert "example.com" not in cookie_contents(client)
    assert flashes(client.get("/settings/remove")) == [f"We sent a confirmation code to {EMAIL}."]
    assert flashes(client.get("/settings/remove")) == []

