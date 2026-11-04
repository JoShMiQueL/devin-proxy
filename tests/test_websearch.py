import asyncio
import os

import pytest

from devin_proxy.transport.auth import Auth
from devin_proxy.transport.websearch import web_search


@pytest.mark.skipif(
    not os.environ.get("DEVIN_PROXY_LIVE"),
    reason="live API test — set DEVIN_PROXY_LIVE=1 to run")
def test_web_search_smoke():
    auth = Auth("https://server.codeium.com")
    results = asyncio.run(web_search(
        "https://server.codeium.com", auth.api_key(), "",
        "python keylogger pynput", timeout=15))
    assert isinstance(results, list)
    assert len(results) > 0
    for r in results:
        assert "url" in r and "title" in r
