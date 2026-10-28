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

"""The email address in the session cookie, encrypted.

Kilo stores only the address's hash, but the pages need the address itself: the header, the
printed page, the export's file name, the removal code's mail and the proposed public id. It
lives in the session, and Flask's session cookie is signed, not encrypted: anyone who sees the
cookie (a shared computer, a browser extension, a proxy log) could read it. So the address is
kept there encrypted (Fernet: AES with an HMAC) with a key derived from SECRET_KEY; changing
SECRET_KEY signs everyone out anyway.

`SIGNED_IN` holds the address of the signed-in user, `PENDING` that of a sign-in waiting for
its code. Cookies from before this kept the address readable as "email" / "pending_email";
`adopt_plaintext()` encrypts those at their next request.

The "we sent a code to <address>" notices would carry the address too: a flash message waits in
the cookie, readable, until the next page shows it. So a route only notes which notice is due
(`announce_code_sent`), and the page that asks for the code turns it into the notice while it
renders (`flash_code_sent`), so the message is added and shown in the same request.
"""

import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from flask import current_app, flash, session
from flask_babel import gettext as _

SIGNED_IN = "address"
PENDING = "pending_address"
# The old readable keys and what they become.
PLAINTEXT_KEYS = {"email": SIGNED_IN, "pending_email": PENDING}
# Which "code sent" notice the next code page shows: "signin", "resend" or "removal".
CODE_SENT = "code_sent"


def _fernet():
    """A Fernet with its own key from SECRET_KEY (never SECRET_KEY itself, which also signs the cookie)."""
    secret = current_app.secret_key
    if isinstance(secret, str):
        secret = secret.encode()
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"kilo session address").derive(secret)
    return Fernet(base64.urlsafe_b64encode(key))


def store(key, email):
    """Put `email` in the session under `key`, encrypted."""
    session[key] = _fernet().encrypt(email.encode()).decode()


def read(key):
    """The address under `key`, or None: none stored, or one that does not decrypt (made with
    another SECRET_KEY)."""
    token = session.get(key)
    if not token:
        return None
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def signed_in():
    """The signed-in user's address, or None."""
    return read(SIGNED_IN)


def adopt_plaintext():
    """Encrypt an address a cookie from before still carries readable."""
    for old, new in PLAINTEXT_KEYS.items():
        email = session.pop(old, None)
        if email:
            store(new, email)


def announce_code_sent(kind):
    """Have the next code page say that a code went out ("signin", "resend" or "removal")."""
    session[CODE_SENT] = kind


def flash_code_sent():
    """The notice `announce_code_sent` asked for, with the address; call it just before rendering
    the page that shows it. Nothing without one, or when the address does not decrypt."""
    kind = session.pop(CODE_SENT, None)
    email = signed_in() if kind == "removal" else read(PENDING)
    if kind is None or email is None:
        return
    if kind == "signin":
        flash(_("We sent a verification code to %(email)s.", email=email), "success")
    elif kind == "resend":
        flash(_("We sent a new code to %(email)s.", email=email), "success")
    else:
        flash(_("We sent a confirmation code to %(email)s.", email=email), "success")
