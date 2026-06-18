from __future__ import annotations

import logging
import re
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


DEFAULT_MAX_PAGES = 20


_RESULT_RANGE_RE = re.compile(
    r"(\d+)\s*-\s*(\d+)\s+de\s+(\d+)\s+Resultados", re.IGNORECASE
)


_PAGER_ICON_PATTERNS = {
    "first": re.compile(r"FirstButton", re.IGNORECASE),
    "previous": re.compile(r"PreviousButton", re.IGNORECASE),
    "next": re.compile(r"NextButton", re.IGNORECASE),
    "last": re.compile(r"LastButton", re.IGNORECASE),
}


def search_tenders(
    session: PoliteSession, query: str, max_pages: int = DEFAULT_MAX_PAGES
) -> list[str]:
    
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

    form_data = _collect_form_state(form)
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

    action = form.get("action")
    if not action:
        logger.warning("Search form has no action URL for query %r", query)
        return []
    post_url = urljoin(response.url, action)

    all_urls: list[str] = []
    page_num = 1

    while True:
        try:
            results_response = session.post(post_url, data=form_data)
        except Exception:
            logger.exception(
                "Failed to submit PLACSP search (page %d) for query %r",
                page_num,
                query,
            )
            break

        results_soup = BeautifulSoup(results_response.text, "html.parser")
        page_urls = _extract_detail_urls(results_soup, results_response.url)
        for url in page_urls:
            if url not in all_urls:
                all_urls.append(url)

        range_info = _extract_result_range(results_soup)
        if range_info:
            start, end, total = range_info
            logger.info(
                "Query %r page %d: results %d-%d of %d (%d detail link(s))",
                query,
                page_num,
                start,
                end,
                total,
                len(page_urls),
            )
            if end >= total:
                break  # last page reached
        else:
            logger.debug(
                "Query %r page %d: no 'N - M de T Resultados' header found; "
                "relying on Next-button presence to detect the last page.",
                query,
                page_num,
            )

        if page_num >= max_pages:
            logger.info(
                "Reached max_pages=%d for query %r; stopping pagination "
                "(more results may exist).",
                max_pages,
                query,
            )
            break

        next_form = results_soup.find("form")
        if next_form is None:
            logger.warning(
                "No <form> on results page %d for query %r; stopping.",
                page_num,
                query,
            )
            break

        next_button_name = _find_pager_button_name(next_form, "next")
        if next_button_name is None:
            logger.info(
                "No 'Next' pager button found for query %r after page %d "
                "(likely the last page); stopping.",
                query,
                page_num,
            )
            break

        # Rebuild form_data from THIS page's form -- the ViewState (and
        # possibly other hidden tokens) changes on every postback, so we
        # can't reuse the dict from the previous iteration.
        form_data = _collect_form_state(next_form)
        form_data[next_button_name] = ""
        form_data[f"{next_button_name}.x"] = "1"
        form_data[f"{next_button_name}.y"] = "1"
        next_action = next_form.get("action")
        if next_action:
            post_url = urljoin(results_response.url, next_action)

        page_num += 1

    if not all_urls:
        logger.warning(
            "No tender detail links found across %d page(s) for query %r. "
            "The result page structure may have changed, or the search "
            "may not have returned results.",
            page_num,
            query,
        )

    return all_urls


def _collect_form_state(form) -> dict[str, str]:
    """Collect all input name/value pairs from `form` (text + hidden).

    This preserves JSF view-state, CSRF tokens, etc. so that re-POSTing
    this dict (with one field changed) looks like a real postback from the
    same session rather than a fresh request.
    """
    form_data: dict[str, str] = {}
    for input_tag in form.find_all("input"):
        name = input_tag.get("name")
        if not name:
            continue
        input_type = (input_tag.get("type") or "text").lower()
        if input_type in ("submit", "image", "button", "reset"):
            # Don't include other clickable buttons' own name/value pairs
            # -- only the one we're actually "clicking" should be present
            # in the submitted data, exactly like a real browser submit.
            continue
        form_data[name] = input_tag.get("value", "")
    return form_data


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


def _find_pager_button_name(form, which: str) -> str | None:
    
    pattern = _PAGER_ICON_PATTERNS[which]
    for input_tag in form.find_all("input", {"type": "image"}):
        src = input_tag.get("src", "")
        if pattern.search(src):
            return input_tag.get("name")
    return None


def _extract_result_range(soup: BeautifulSoup) -> tuple[int, int, int] | None:
    """Parse "26 - 50 de 291 Resultados" -> (26, 50, 291), or None."""
    match = _RESULT_RANGE_RE.search(soup.get_text(" ", strip=True))
    if not match:
        return None
    start, end, total = (int(g) for g in match.groups())
    return start, end, total


def _find_results_container(soup: BeautifulSoup):
 
    container = soup.find(id=lambda v: bool(v) and "tableResultSearch" in v)
    if container is None:
        logger.warning(
            "Could not find the 'tableResultSearch' results container; "
            "falling back to scanning the whole page for detail links "
            "(this risks picking up unrelated 'recent tenders' sidebar "
            "content -- verify output for this query manually)."
        )
        return soup
    return container


def _extract_detail_urls(soup: BeautifulSoup, base_url: str) -> list[str]:
    
    results_container = _find_results_container(soup)
    urls: list[str] = []
    for anchor in results_container.find_all("a", href=True):
        href = anchor["href"]
        if _looks_like_detail_link(href):
            absolute = urljoin(base_url, href)
            if absolute not in urls:
                urls.append(absolute)
    return urls


_DETAIL_LINK_MARKERS = (
    "deeplink:detalle_licitacion",
    "doc_can_adj",
    "detalle",
)


def _looks_like_detail_link(href: str) -> bool:
    """True if `href` looks like a tender detail-page link (any known PLACSP format)."""
    lowered = href.lower()
    return any(marker in lowered for marker in _DETAIL_LINK_MARKERS)
