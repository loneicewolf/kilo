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
"""

import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from flask import current_app, session

SIGNED_IN = "address"
PENDING = "pending_address"
# The old readable keys and what they become.
PLAINTEXT_KEYS = {"email": SIGNED_IN, "pending_email": PENDING}


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
