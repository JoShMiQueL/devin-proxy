"""Process entrypoint: settings -> auth -> engine -> uvicorn."""
from __future__ import annotations

import logging
import sys
import threading

import uvicorn

from .api.routes import build_app
from .config import load_settings
from .jailbreak.override import OverridePrompt
from .pipeline import Engine
from .transport.auth import Auth


def serve(host: str | None = None, port: int | None = None) -> int:
    overrides = {k: v for k, v in (("host", host), ("port", port)) if v is not None}
    settings = load_settings(**overrides)
    logging.basicConfig(
        level=logging.INFO,
        format="[devin-proxy] %(message)s",
        stream=sys.stderr)

    auth = Auth(settings.backend, client_version=settings.client_version)
    override = OverridePrompt(settings.system_file)

    # Prefetch the model catalog in the background — it costs ~1s of
    # Connect-RPC round-trips and /health doesn't need it. Routes degrade
    # gracefully (catalog=None -> default routing) until it lands.
    catalog = None
    catalog_done = threading.Event()

    def _fetch():
        nonlocal catalog
        try:
            import asyncio

            from .models.fetch import fetch_catalog
            catalog = asyncio.new_event_loop().run_until_complete(
                fetch_catalog(settings.backend, auth.api_key(), "",
                              settings.client_version))
            if catalog:
                app.state.catalog = catalog
                engine.catalog = catalog
        except Exception as e:
            log = logging.getLogger("devin-proxy")
            log.warning("catalog prefetch skipped: %s", e)
        finally:
            catalog_done.set()

    threading.Thread(target=_fetch, daemon=True, name="catalog-fetch").start()

    engine = Engine(settings, auth, override, catalog)
    app = build_app(settings, auth, engine, override, catalog)

    log = logging.getLogger("devin-proxy")
    log.info("listening on %s:%d -> %s (allowed=%s%s) override=%dc",
             settings.host, settings.port, settings.backend,
             ",".join(settings.allowed_models),
             "+paid" if settings.allow_paid else "",
             len(override.load()))
    try:
        auth.api_key()
        log.info("devin credentials ok (%s)", auth.credentials)
    except Exception as e:
        log.warning("credentials unavailable: %s", e)
    log.info("catalog prefetch running in background — /v1/models and "
             "allow_paid routing degraded until it lands")

    uvicorn.run(app, host=settings.host, port=settings.port,
                log_level="warning", access_log=False)
    return 0


def main():
    from .cli import main as cli_main
    return cli_main()


if __name__ == "__main__":
    raise SystemExit(main())
