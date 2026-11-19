"""HTTPS requests that work on a fresh Windows install.

Python checks certificates against the Windows certificate store. Windows
only downloads some root certificates the first time a browser needs them,
which Python cannot trigger, so a request can fail with
CERTIFICATE_VERIFY_FAILED depending on which server answers. Trusting the
certifi bundle as well as the Windows store avoids that.
"""

from __future__ import annotations

import ssl
import urllib.request

_context: ssl.SSLContext | None = None


def _ssl_context() -> ssl.SSLContext:
    global _context
    if _context is None:
        context = ssl.create_default_context()   # the Windows store
        try:
            import certifi
            context.load_verify_locations(cafile=certifi.where())
        except (ImportError, OSError, ssl.SSLError):
            pass
        _context = context
    return _context


def urlopen(request: urllib.request.Request, timeout: float):
    """urllib.request.urlopen with the certificate fix above."""
    return urllib.request.urlopen(request, timeout=timeout, context=_ssl_context())
