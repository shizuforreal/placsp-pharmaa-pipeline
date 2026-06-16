"""
Search PLACSP for a given free-text query and return detail-page URLs.

How PLACSP search actually works
----------------------------------
The public search UI at
    https://contrataciondelestado.es/wps/portal/plataforma/buscador/

is a Liferay/JSF portlet. Every link on the page (including the search
results) is a "deep link" of the form `.../wps/portal/.../!ut/p/z1/<token>`,
where `<token>` encodes portlet view-state that is normally only valid
within the browser session that generated it. A plain `requests.get()` to
the search URL returns the *empty* search form, not results -- the results
are produced by a server-side form POST tied to that session's view-state.

What this module does
----------------------
1. GETs the search portal page to establish a session (cookies) and to try
   to locate the hidden JSF view-state field and form action URL.
2. POSTs the search term as a JSF form submission using that view-state.
3. Parses the returned HTML for result rows and extracts the detail-page
   "deeplink" URLs (the same kind of URL you get by clicking "Detalle de la
   licitación", e.g.
   .../wps/poc?uri=deeplink:detalle_licitacion&idEvl=...).

Known limitation
------------------
JSF view-state tokens can be short-lived, environment-specific, or rejected
for automated clients regardless of User-Agent. If this module cannot find
a view-state field, or the POST does not return recognisable result rows, it
logs a clear warning and returns an empty list rather than failing the whole
pipeline. See README.md "Limitations" for how the pipeline still produces a
useful CSV in that case (via the `--seed-urls` fallback).
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from pipeline.http_client import PoliteSession

logger = logging.getLogger(__name__)

SEARCH_PAGE_URL = (
    "https://contrataciondelestado.es/wps/portal/plataforma/buscador/"
)

# Field name PLACSP uses for the free-text search box, as seen in the
# screenshot the user supplied ("Texto a buscar:").
SEARCH_TEXT_FIELD_CANDIDATES = (
    "textoBusqueda",
    "texto",
    "_buscarLicitacionesPortlet_INSTANCE_buscarLicitaciones:textoLibre",
)


def search_tenders(session: PoliteSession, query: str) -> list[str]:
    """Search PLACSP for `query` and return a list of detail-page URLs.

    Returns an empty list (with a logged warning) if the search form
    cannot be located or submitted programmatically -- this is treated as
    a recoverable condition, not a fatal error, since the JSF portal can
    refuse automated submissions even with correct headers.
    """
    logger.info("Searching PLACSP for molecule query: %r", query)

    try:
        response = session.get(SEARCH_PAGE_URL)
    except Exception:
        logger.exception("Failed to load PLACSP search page for query %r", query)
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    form = soup.find("form")
    if form is None:
        logger.warning(
            "No <form> found on PLACSP search page; cannot submit search "
            "for %r programmatically.",
            query,
        )
        return []

    action = form.get("action")
    if not action:
        logger.warning("Search form has no action URL for query %r", query)
        return []

    post_url = urljoin(response.url, action)

    # Collect all existing hidden/text inputs so we preserve JSF view-state,
    # CSRF tokens, etc. that the form already carries.
    form_data: dict[str, str] = {}
    for input_tag in form.find_all("input"):
        name = input_tag.get("name")
        if not name:
            continue
        form_data[name] = input_tag.get("value", "")

    # Inject our search term into whichever field looks like the text box.
    search_field_name = _find_search_field_name(form, form_data)
    if search_field_name is None:
        logger.warning(
            "Could not identify the search text field on PLACSP's form "
            "for query %r; form had fields: %s",
            query,
            sorted(form_data.keys()),
        )
        return []

    form_data[search_field_name] = query

    try:
        results_response = session.post(post_url, data=form_data)
    except Exception:
        logger.exception("Failed to submit PLACSP search for query %r", query)
        return []

    return _extract_detail_urls(results_response.text, results_response.url)


def _find_search_field_name(form, form_data: dict[str, str]) -> str | None:
    """Best-effort identification of the free-text search field's `name`."""
    # 1. Direct name match against known candidates.
    for candidate in SEARCH_TEXT_FIELD_CANDIDATES:
        if candidate in form_data:
            return candidate

    # 2. Fall back to: any visible <input type="text"> whose id/name suggests
    #    it's the free-text search box.
    for input_tag in form.find_all("input", {"type": "text"}):
        identifier = (input_tag.get("name") or "") + (input_tag.get("id") or "")
        if any(hint in identifier.lower() for hint in ("texto", "busqueda", "search")):
            return input_tag.get("name")

    return None


def _extract_detail_urls(html: str, base_url: str) -> list[str]:
    """Parse a PLACSP results page and return absolute detail-page URLs.

    Looks for anchors whose href contains `deeplink:detalle_licitacion`,
    which is the pattern seen in the user's worked example
    (".../wps/poc?uri=deeplink:detalle_licitacion&idEvl=...").
    """
    soup = BeautifulSoup(html, "html.parser")

    urls: list[str] = []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if "deeplink:detalle_licitacion" in href or "DOC_CAN_ADJ" in href:
            absolute = urljoin(base_url, href)
            if absolute not in urls:
                urls.append(absolute)

    if not urls:
        logger.warning(
            "No tender detail links found in PLACSP search results page "
            "(base_url=%s). The result page structure may have changed, "
            "or the search may not have returned results.",
            base_url,
        )

    return urls
