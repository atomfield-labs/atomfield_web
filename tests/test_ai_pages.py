"""
Reading a task's listed pages: only the parts that matter, a copy kept for
a while, and an unreachable page never stops the review.
"""

import asyncio
from pathlib import Path

import httpx
import pytest

from app.ai.pages import (
    KEEP_SECONDS,
    PageLibrary,
    excerpt,
    text_of_html,
)
from app.catalog.models import ReferencePage

ADDRESS = "https://docs.example.org/input.html"
PAGE = ReferencePage(title="Input", page=ADDRESS)
# Cut down from Quantum ESPRESSO's pw.x input page, with its index line.
MANUAL = """
<html><head><style>p {color: red}</style><script>var x = 1;</script></head>
<body><nav>mixing_beta in a menu</nav>
<table><tr><td>electron_maxstep | conv_thr | mixing_mode | mixing_beta |
mixing_ndim</td></tr></table>
<p>For a RISM run mixing_beta is 0.2 in both solvers.</p>
<table>
<tr><th>electron_maxstep</th></tr>
<tr><td>INTEGER</td></tr><tr><td>Default: 100</td></tr>
<tr><td>maximum number of iterations in a scf step.</td></tr>
</table>
<table>
<tr><th>mixing_beta</th></tr>
<tr><td>REAL</td></tr><tr><td>Default: 0.7D0</td></tr>
<tr><td>mixing factor for self-consistency</td></tr>
</table>
<footer>mixing_beta in a footer</footer>
</body></html>
"""


class MemoryStore:
    """
    A store in memory, of the two calls the library makes.
    """

    def __init__(self) -> None:
        """
        Start empty.
        """
        self.files: dict[str, bytes] = {}

    async def read(self, key: str) -> bytes | None:
        """
        Read a file.

        :param key: The file.
        :type key: str
        :return: Its content, or None if absent.
        :rtype: bytes | None
        """
        return self.files.get(key)

    async def write(self, key: str, data: bytes) -> None:
        """
        Write a file.

        :param key: The file.
        :type key: str
        :param data: Its content.
        :type data: bytes
        """
        self.files[key] = data


class Web:
    """
    A web server in process: counts fetches, and can go down.
    """

    def __init__(self, body: str = MANUAL) -> None:
        """
        :param body: What it serves.
        :type body: str
        """
        self.body = body
        self.status = 200
        self.fetches = 0

    def client(self) -> httpx.AsyncClient:
        """
        A client that reaches only this server.

        :return: The client.
        :rtype: httpx.AsyncClient
        """

        def answer(request: httpx.Request) -> httpx.Response:
            """
            Answer one request.

            :param request: The request.
            :type request: httpx.Request
            :return: The page, or the error set.
            :rtype: httpx.Response
            """
            self.fetches += 1
            return httpx.Response(self.status, text=self.body)

        return httpx.AsyncClient(transport=httpx.MockTransport(answer))


def test_a_page_loses_its_scripts_and_menus():
    """
    What's left is the text a person reads.
    """
    text = text_of_html(MANUAL)
    assert "var x" not in text
    assert "color: red" not in text
    assert "in a menu" not in text
    assert "in a footer" not in text
    assert "mixing factor for self-consistency" in text


def test_the_entry_for_a_name_comes_before_passing_mentions():
    """
    With room for one part, the part is the entry, not the mention in
    another setting's note, and never the index that only lists names.
    """
    text = text_of_html(MANUAL)
    part = excerpt(text, ["mixing_beta"], 100)
    assert part.startswith("mixing_beta\nREAL")
    assert "mixing factor" in part
    assert "RISM" not in part
    assert "mixing_ndim" not in part


def test_the_budget_holds_and_parts_keep_the_pages_order():
    """
    The real page is 121 KB; a few terms must never bring back much.
    """
    text = "\n".join(
        [f"name_{index}\nREAL\nabout {index}\n" * 3 for index in range(99)]
    )
    terms = ["name_50", "name_2", "name_90"]
    part = excerpt(text, terms, 1000)
    assert len(part) <= 1000 + len("\n...\n") * 3
    assert part.index("name_") == 0


def test_terms_match_whole_words_only():
    """
    ``conv_thr`` isn't a mention of ``thr``.
    """
    assert excerpt("conv_thr\nthe threshold", ["thr"], 100) == ""


def test_a_copy_is_kept_and_used_until_it_is_old():
    """
    A manual is fetched once a month, not once a click.
    """
    web = Web()
    store = MemoryStore()
    now = [1000.0]
    library = PageLibrary(store, web.client(), clock=lambda: now[0])
    first = asyncio.run(library.text_of(PAGE))
    second = asyncio.run(library.text_of(PAGE))
    assert first == second
    assert "mixing factor" in first
    assert web.fetches == 1
    now[0] += KEEP_SECONDS + 1
    asyncio.run(library.text_of(PAGE))
    assert web.fetches == 2


def test_an_old_copy_is_better_than_nothing():
    """
    If the site is down when a copy is old, the old copy is used.
    """
    web = Web()
    now = [1000.0]
    library = PageLibrary(MemoryStore(), web.client(), clock=lambda: now[0])
    asyncio.run(library.text_of(PAGE))
    web.status = 500
    now[0] += KEEP_SECONDS + 1
    assert "mixing factor" in asyncio.run(library.text_of(PAGE))


def test_an_unreadable_page_is_named_and_the_rest_are_read():
    """
    A page that can't be read never stops a review.
    """
    web = Web()
    web.status = 404
    guide = ReferencePage(title="Guide", page="docs/quantum-espresso.md")
    library = PageLibrary(MemoryStore(), web.client())
    found = asyncio.run(library.parts_about([PAGE, guide], ["pw.x"], 4000))
    assert found.unread == ["Input"]
    assert set(found.parts) == {"Guide"}
    assert "pw.x" in found.parts["Guide"]
    assert web.fetches == 1


def test_a_page_with_no_mention_adds_nothing():
    """
    A page about something else isn't sent at all.
    """
    library = PageLibrary(MemoryStore(), Web().client())
    found = asyncio.run(library.parts_about([PAGE], ["no_such_term"], 4000))
    assert found.parts == {}
    assert found.unread == []


def test_a_missing_guide_is_unread_rather_than_an_error():
    """
    A guide listed but not in ``docs/`` is reported like any other page.
    """
    guide = ReferencePage(title="Gone", page="docs/no-such-guide.md")
    library = PageLibrary(MemoryStore(), Web().client())
    found = asyncio.run(library.parts_about([guide], ["pw.x"], 4000))
    assert found.unread == ["Gone"]


@pytest.mark.parametrize("name", ["quantum-espresso.md", "ahc-pipeline.md"])
def test_the_guides_steps_will_list_exist(name: str):
    """
    The guides the task files name are in the repository.

    :param name: A guide.
    :type name: str
    """
    assert (Path(__file__).resolve().parents[1] / "docs" / name).exists()
