"""
Reading the pages a task lists: fetch them, keep a copy for a while, and
pick out only the parts that mention what went wrong. A long manual would
otherwise cost the person more than everything else in the request.

The addresses come only from the catalog, so nothing a log or a model
says can make the server fetch anything.
"""

import hashlib
import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path

import httpx

from app.catalog.models import ReferencePage
from app.storage.store import ArtifactStore

DOCS_PARENT = Path(__file__).resolve().parents[2]
GUIDE_PREFIX = "docs/"
PAGE_FOLDER = "ai/pages"
ENCODING = "utf-8"
USER_AGENT = "AtomField (reads documentation pages for AI help)"
PAGE_TIMEOUT_SECONDS = 15.0
PAGE_MAX_BYTES = 4 * 1024 * 1024
KEEP_SECONDS = 30 * 24 * 3600.0
# How much follows a mention: enough for an entry's type and description.
PART_CHARACTERS = 900
# How far around a mention to look for a line that only lists names.
LIST_LOOK_CHARACTERS = 40
LIST_SEPARATOR = "|"
LIST_SEPARATORS_MIN = 3
SKIPPED_TAGS = frozenset({"footer", "header", "nav", "script", "style", "svg"})
BLOCK_TAGS = frozenset(
    {
        "br",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "li",
        "p",
        "pre",
        "section",
        "table",
        "td",
        "th",
        "tr",
    }
)


class PageText(HTMLParser):
    """
    The readable text of an HTML page, one line per block.
    """

    def __init__(self) -> None:
        """
        Start with nothing read.
        """
        super().__init__()
        self.skipping = 0
        self.pieces: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        """
        Note a tag opening.

        :param tag: The tag.
        :type tag: str
        :param attrs: Its attributes, unused.
        :type attrs: list
        """
        self.skipping += tag in SKIPPED_TAGS
        if tag in BLOCK_TAGS:
            self.pieces.append("\n")

    def handle_endtag(self, tag: str) -> None:
        """
        Note a tag closing.

        :param tag: The tag.
        :type tag: str
        """
        if tag in SKIPPED_TAGS and self.skipping:
            self.skipping -= 1
        if tag in BLOCK_TAGS:
            self.pieces.append("\n")

    def handle_data(self, data: str) -> None:
        """
        Keep text, unless it is inside something skipped.

        :param data: The text.
        :type data: str
        """
        if not self.skipping:
            self.pieces.append(data)


def text_of_html(html: str) -> str:
    """
    The readable text of a page, without its scripts and menus.

    :param html: The page.
    :type html: str
    :return: Its text, with spaces and blank lines tidied.
    :rtype: str
    """
    parser = PageText()
    parser.feed(html)
    tidied = re.sub(r"[ \t]+", " ", "".join(parser.pieces))
    return re.sub(r"\n\s*\n+", "\n", tidied).strip()


def in_a_list_of_names(text: str, position: int) -> bool:
    """
    Whether a mention is on a line that only lists names, such as a
    manual's index, which says nothing about the name.

    :param text: The page's text.
    :type text: str
    :param position: Where the mention starts.
    :type position: int
    :return: True in such a line.
    :rtype: bool
    """
    start = max(0, position - LIST_LOOK_CHARACTERS)
    around = text[start : position + LIST_LOOK_CHARACTERS]
    return around.count(LIST_SEPARATOR) >= LIST_SEPARATORS_MIN


def stands_alone(text: str, match: re.Match) -> bool:
    """
    Whether a mention is alone on its line, which is how manuals mark the
    entry for a name, rather than a passing mention of it.

    :param text: The page's text.
    :type text: str
    :param match: The mention.
    :type match: re.Match
    :return: True if nothing else is on the line.
    :rtype: bool
    """
    start = text.rfind("\n", 0, match.start()) + 1
    end = text.find("\n", match.end())
    line = text[start : end if end >= 0 else len(text)]
    return line.strip().lower() == match.group().lower()


def mentions(text: str, terms: Sequence[str]) -> list[tuple[bool, int, int]]:
    """
    Every useful mention of the terms, best first: entries before passing
    mentions, then earlier terms before later ones.

    :param text: The page's text.
    :type text: str
    :param terms: What to look for, most important first.
    :type terms: Sequence[str]
    :return: (is a passing mention, term's place, position), sorted.
    :rtype: list[tuple[bool, int, int]]
    """
    found = []
    for place, term in enumerate(terms):
        pattern = re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)
        for match in pattern.finditer(text):
            if not in_a_list_of_names(text, match.start()):
                found.append(
                    (not stands_alone(text, match), place, match.start())
                )
    return sorted(found)


def excerpt(text: str, terms: Sequence[str], budget: int) -> str:
    """
    The parts of a page about these terms, in the page's own order.

    :param text: The page's text.
    :type text: str
    :param terms: What to look for, most important first.
    :type terms: Sequence[str]
    :param budget: Most characters to keep.
    :type budget: int
    :return: The parts, separated by ``...``; empty if none mention them.
    :rtype: str
    """
    chosen: list[tuple[int, int]] = []
    used = 0
    for _, _, position in mentions(text, terms):
        end = min(len(text), position + PART_CHARACTERS)
        fresh = not any(a < end and position < b for a, b in chosen)
        if fresh and used + end - position <= budget:
            chosen.append((position, end))
            used += end - position
    return "\n...\n".join(text[a:b] for a, b in sorted(chosen))


@dataclass(frozen=True, slots=True)
class PageParts:
    """
    What was read from a task's pages.

    :param parts: Page title -> the parts about the terms.
    :type parts: dict[str, str]
    :param unread: Titles of pages that couldn't be read.
    :type unread: list[str]
    """

    parts: dict[str, str] = field(default_factory=dict)
    unread: list[str] = field(default_factory=list)


class PageLibrary:
    """
    Gives the text of listed pages, keeping a copy so that a manual is
    fetched once a month rather than once a click.
    """

    def __init__(
        self,
        store: ArtifactStore,
        http: httpx.AsyncClient,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """
        :param store: Where copies are kept.
        :type store: ArtifactStore
        :param http: Fetches pages.
        :type http: httpx.AsyncClient
        :param clock: The time now, in seconds; tests set it.
        :type clock: Callable[[], float]
        """
        self.store = store
        self.http = http
        self.clock = clock

    async def fetch(self, address: str) -> str | None:
        """
        Fetch a web page's text.

        :param address: The page, from the catalog.
        :type address: str
        :return: Its text, or None if it can't be read just now.
        :rtype: str | None
        """
        headers = {"User-Agent": USER_AGENT}
        try:
            response = await self.http.get(
                address,
                headers=headers,
                timeout=PAGE_TIMEOUT_SECONDS,
                follow_redirects=True,
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return None
        body = response.content[:PAGE_MAX_BYTES]
        return text_of_html(body.decode(ENCODING, "ignore"))

    async def read_copy(self, key: str) -> tuple[float, str] | None:
        """
        Read the copy kept of a page.

        :param key: Where it is kept.
        :type key: str
        :return: (when it was fetched, its text); None if there is none.
        :rtype: tuple[float, str] | None
        """
        kept = await self.store.read(key)
        if kept is None:
            return None
        stamp, _, text = kept.decode(ENCODING).partition("\n")
        return float(stamp), text

    async def web_page(self, address: str) -> str | None:
        """
        A web page's text: the copy while it is fresh, then a new fetch,
        then an old copy rather than nothing.

        :param address: The page.
        :type address: str
        :return: Its text, or None if it can't be had at all.
        :rtype: str | None
        """
        name = hashlib.sha256(address.encode(ENCODING)).hexdigest()
        key = f"{PAGE_FOLDER}/{name}.txt"
        copy = await self.read_copy(key)
        if copy is not None and self.clock() - copy[0] < KEEP_SECONDS:
            return copy[1]
        text = await self.fetch(address)
        if text is None:
            return copy[1] if copy is not None else None
        kept = f"{self.clock()}\n{text}".encode(ENCODING)
        await self.store.write(key, kept)
        return text

    async def text_of(self, page: ReferencePage) -> str | None:
        """
        A listed page's text.

        :param page: The page: a web address or a guide in ``docs/``.
        :type page: ReferencePage
        :return: Its text, or None if it can't be read.
        :rtype: str | None
        """
        if not page.page.startswith(GUIDE_PREFIX):
            return await self.web_page(page.page)
        try:
            return (DOCS_PARENT / page.page).read_text(encoding=ENCODING)
        except OSError:
            return None

    async def parts_about(
        self, pages: Sequence[ReferencePage], terms: Sequence[str], budget: int
    ) -> PageParts:
        """
        The parts of a task's pages about these terms. Each page gets its
        share of the budget.

        :param pages: The task's pages.
        :type pages: Sequence[ReferencePage]
        :param terms: What to look for, most important first.
        :type terms: Sequence[str]
        :param budget: Most characters in all.
        :type budget: int
        :return: The parts, and which pages couldn't be read.
        :rtype: PageParts
        """
        found = PageParts()
        share = budget // max(1, len(pages))
        for page in pages:
            text = await self.text_of(page)
            if text is None:
                found.unread.append(page.title)
            elif parts := excerpt(text, terms, share):
                found.parts[page.title] = parts
        return found
