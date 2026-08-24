import hashlib
import hmac
import time

import pytest
from fastapi import HTTPException

from bridges.mt5.app import verify


def test_signed_message_and_replay_window():
    secret = b"secret"
    body = b"{}"
    timestamp = str(int(time.time()))
    sig = hmac.new(secret, timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    verify(body, timestamp, sig, secret)
    with pytest.raises(HTTPException):
        verify(body, str(int(time.time()) - 100), sig, secret)
