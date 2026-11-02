"""
What a review reads about a step: the right files, trimmed as the recipes
say, with every trim recorded.
"""

import asyncio
import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.ai.evidence import (
    RECIPES,
    Evidence,
    EvidenceCollector,
    FileGroup,
    ReviewKind,
    error_words,
    fair_shares,
    group_of,
    thinned_plots,
)
from app.ai.pages import PageLibrary
from app.ai.prompts import (
    ANSWER_SHAPE,
    build_question,
    render_evidence,
    setting_values,
)
from app.catalog.catalog import Catalog
from app.catalog.models import ReferencePage
from app.storage.keys import job_file_key
from tests.test_ai_pages import MANUAL, MemoryStore, Web

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "catalog.json"
TASK = Catalog.from_path(FIXTURE).get("toy_opt")
WEB_PAGE = ReferencePage(title="Input", page="https://docs.example.org/a")


def job_with(
    store: MemoryStore, files: dict[str, str], **fields
) -> SimpleNamespace:
    """
    A job whose agent uploaded these files, and left one big file behind.

    :param store: Where the uploads go.
    :type store: MemoryStore
    :param files: Name -> text.
    :type files: dict[str, str]
    :param fields: Other fields of the job.
    :type fields: Any
    :return: Enough of a job.
    :rtype: SimpleNamespace
    """
    job = SimpleNamespace(
        id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        node_key="step_one",
        script_name="toy_opt",
        status="failed",
        attempt=1,
        error_message=None,
        input_files={},
        parameters={"temp": 310.0, "pipeline_id": "bookkeeping"},
        output_files=[
            *(
                {"path": name, "size_bytes": len(text), "uploaded": True}
                for name, text in files.items()
            ),
            {"path": "scf.wfc", "size_bytes": 9_000_000, "uploaded": False},
        ],
    )
    for name, value in fields.items():
        setattr(job, name, value)
    for name, text in files.items():
        key = job_file_key(job.run_id, job.id, name)
        store.files[key] = text.encode("utf-8")
    return job


def collect(
    store: MemoryStore,
    job: SimpleNamespace,
    kind: ReviewKind,
    pages: tuple = (),
    parents: tuple = (),
    web: Web | None = None,
) -> Evidence:
    """
    Run the collector.

    :param store: Where the uploads are.
    :type store: MemoryStore
    :param job: The job.
    :type job: SimpleNamespace
    :param kind: The kind of review.
    :type kind: ReviewKind
    :param pages: The task's pages.
    :type pages: tuple
    :param parents: The jobs before it.
    :type parents: tuple
    :param web: Serves the pages.
    :type web: Web | None
    :return: The evidence.
    :rtype: Evidence
    """
    library = PageLibrary(store, (web or Web()).client())
    collector = EvidenceCollector(store, library)
    return asyncio.run(collector.collect(job, TASK, pages, parents, kind))


def by_name(evidence: Evidence) -> dict:
    """
    The parts of some evidence, by name.

    :param evidence: The evidence.
    :type evidence: Evidence
    :return: Name -> part.
    :rtype: dict
    """
    return {part.name: part for part in evidence.parts}


def test_a_long_log_gives_its_end_and_says_so():
    """
    The end of a log is where the failure is, and the cut is recorded.
    """
    store = MemoryStore()
    budget = RECIPES[ReviewKind.FIX].groups[FileGroup.LOGS]
    log = "start\n" + "x" * budget + "\nthe real error"
    job = job_with(store, {"toy_opt.log": log})
    part = by_name(collect(store, job, ReviewKind.FIX))["toy_opt.log"]
    assert part.text.endswith("the real error")
    assert "start" not in part.text
    assert len(part.text) == budget
    assert part.shown == f"last {budget:,} characters"


def test_a_short_file_is_given_whole():
    """
    Nothing is cut that doesn't need to be.
    """
    store = MemoryStore()
    job = job_with(store, {"toy_opt.log": "short log"})
    part = by_name(collect(store, job, ReviewKind.FIX))["toy_opt.log"]
    assert part.text == "short log"
    assert part.shown == "all"


def test_a_long_input_gives_its_start_and_a_table_both_ends():
    """
    An input's settings are at its start; a table shows its range from
    both ends.
    """
    store = MemoryStore()
    budget = RECIPES[ReviewKind.ANALYSIS].groups
    deck = "&control\n" + "y" * budget[FileGroup.INPUTS]
    table = "first row\n" + "z" * budget[FileGroup.DECLARED] + "\nlast row"
    job = job_with(store, {"scf.in": deck, "a_optimized.xyz": table})
    parts = by_name(collect(store, job, ReviewKind.ANALYSIS))
    assert parts["scf.in"].text.startswith("&control")
    assert parts["scf.in"].shown.startswith("first ")
    assert parts["a_optimized.xyz"].text.startswith("first row")
    assert parts["a_optimized.xyz"].text.endswith("last row")
    assert "first and last" in parts["a_optimized.xyz"].shown


def test_the_recipes_stay_within_about_twenty_thousand_tokens():
    """
    The size the plan promised, at about four characters a token.
    """
    for recipe in RECIPES.values():
        total = sum(recipe.groups.values()) + recipe.parents + recipe.pages
        assert total <= 80_000


def test_files_a_review_should_not_read_stay_out():
    """
    Coordinates that aren't an input or a declared output, and anything
    that isn't text, stay out. Neither is anything not uploaded read.
    """
    store = MemoryStore()
    job = job_with(store, {"toy_opt.log": "log", "frames.xyz": "1\n"})
    parts = by_name(collect(store, job, ReviewKind.FIX))
    assert set(parts) == {"toy_opt.log"}


def test_nothing_from_outside_the_jobs_own_uploads_is_read():
    """
    A file of another job, or one with no card, can't get in.
    """
    store = MemoryStore()
    other = job_with(store, {"secret.log": "another job's log"})
    job = job_with(store, {"toy_opt.log": "mine"})
    store.files[job_file_key(job.run_id, job.id, "script.py")] = b"source"
    parts = by_name(collect(store, job, ReviewKind.FIX))
    assert set(parts) == {"toy_opt.log"}
    assert other.id != job.id


def test_a_declared_or_wired_file_counts_as_that():
    """
    A task's outputs and a job's inputs are told apart from other text.
    """
    wired = frozenset({"start.xyz"})
    assert group_of("a_optimized.xyz", TASK, wired) is FileGroup.DECLARED
    assert group_of("start.xyz", TASK, wired) is FileGroup.INPUTS
    assert group_of("scf.in", TASK, wired) is FileGroup.INPUTS
    assert group_of("scf.out", TASK, wired) is FileGroup.OTHER
    assert group_of("x_plots.json", TASK, wired) is FileGroup.PLOTS
    assert group_of("toy_opt.log", TASK, wired) is FileGroup.LOGS
    assert group_of("frames.xyz", TASK, wired) is None
    assert group_of("restart.bin", TASK, wired) is None


def test_files_left_on_the_cluster_are_named():
    """
    So the model can say when one it needs is missing.
    """
    store = MemoryStore()
    job = job_with(store, {"toy_opt.log": "log"})
    left = collect(store, job, ReviewKind.FIX).left_behind
    assert [(item.name, item.size_bytes) for item in left] == [
        ("scf.wfc", 9_000_000)
    ]


def test_a_budget_goes_to_the_files_that_need_it():
    """
    A small file takes all it needs, and leaves the rest to larger ones.
    """
    shares = fair_shares({"small": 10, "big": 500, "middle": 100}, 300)
    assert shares == {"small": 10, "middle": 100, "big": 190}
    assert sum(shares.values()) == 300


def test_a_fix_reads_no_plots_and_an_analysis_thins_them():
    """
    Plots say nothing about a failure, and a long curve is thinned.
    """
    store = MemoryStore()
    curve = {"name": "E", "x": list(range(2000)), "y": [list(range(2000))]}
    panel = {"x": {"label": "Step"}, "y": {"label": "eV"}, "curves": [curve]}
    plots = {"format": 1, "plots": [{"title": "Energy", "panels": [panel]}]}
    files = {"a_plots.json": json.dumps(plots)}
    job = job_with(store, files)
    assert "a_plots.json" not in by_name(collect(store, job, ReviewKind.FIX))
    part = by_name(collect(store, job, ReviewKind.ANALYSIS))["a_plots.json"]
    kept = json.loads(part.text)[0]["panels"][0]
    assert part.shown == "up to 100 points per line"
    assert kept["x"] == "Step"
    assert len(kept["curves"][0]["x"]) == 100
    assert kept["curves"][0]["y"][0][-1] == 1999


def test_plots_too_big_or_broken_are_left_out_rather_than_cut_in_half():
    """
    Half a JSON document is no use to anyone.
    """
    assert thinned_plots("not json", 1000) is None
    lines = [[1.0] * 50 for _ in range(500)]
    curve = {"name": "bands", "x": [1.0] * 50, "y": lines}
    plots = {"plots": [{"title": "T", "panels": [{"curves": [curve]}]}]}
    assert thinned_plots(json.dumps(plots), 100) is None


def test_the_summaries_of_the_steps_before_are_read():
    """
    A step is often explained by the one before it, and only its summary
    is read.
    """
    store = MemoryStore()
    files = {"a_summary.txt": "Fermi energy 6.2 eV", "a.log": "parent log"}
    parent = job_with(store, files, node_key="scf")
    job = job_with(store, {"toy_opt.log": "log"})
    evidence = collect(store, job, ReviewKind.FIX, parents=(parent,))
    parts = by_name(evidence)
    assert parts["scf/a_summary.txt"].text == "Fermi energy 6.2 eV"
    assert "scf/a.log" not in parts


def test_a_page_is_read_for_the_words_in_the_error():
    """
    Only the matching parts are sent, marked as such, and a page that
    can't be read is named.
    """
    store = MemoryStore()
    log = "starting\nError in mixing_beta handling\n"
    job = job_with(store, {"toy_opt.log": log})
    gone = ReferencePage(title="Gone", page="docs/no-such-guide.md")
    evidence = collect(
        store, job, ReviewKind.FIX, pages=(WEB_PAGE, gone), web=Web(MANUAL)
    )
    part = by_name(evidence)["Input"]
    assert "mixing factor for self-consistency" in part.text
    assert part.shown == "matching parts"
    assert evidence.unread_pages == ["Gone"]


def test_error_words_skip_what_says_nothing():
    """
    Words like ``Error`` match everything; names of routines don't.
    """
    logs = ["all fine here\n", "Error in routine c_bands: not converged\n"]
    words = error_words("Fatal: too many bands", logs)
    assert "c_bands" in words
    assert "bands" in words
    assert "Error" not in words
    assert "routine" not in words
    assert "fine" not in words


def test_what_is_sent_marks_data_and_leaves_out_bookkeeping():
    """
    The text holds the settings by name, with values from the job, and no
    bookkeeping of the platform's.
    """
    store = MemoryStore()
    job = job_with(store, {"toy_opt.log": "the log"}, error_message="it broke")
    evidence = collect(store, job, ReviewKind.FIX)
    text = render_evidence(job, TASK, evidence)
    assert "Error: it broke" in text
    assert '<file name="toy_opt.log" shown="all">\nthe log\n</file>' in text
    assert "- temp (" in text
    assert "now 310.0" in text
    assert "scf.wfc (9,000,000 bytes)" in text
    assert "bookkeeping" not in text
    assert "pipeline_id" not in text


def test_settings_show_defaults_for_what_the_job_left_unset():
    """
    A setting left alone runs at its default.
    """
    store = MemoryStore()
    values = setting_values(job_with(store, {}), TASK)
    assert values["temp"] == 310.0
    assert values["charge"] == 0
    assert "pipeline_id" not in values


@pytest.mark.parametrize(
    ("kind", "words"),
    [(ReviewKind.FIX, "failed"), (ReviewKind.ANALYSIS, "finished")],
)
def test_the_question_says_which_job_it_is_and_demands_the_shape(
    kind: ReviewKind, words: str
):
    """
    A fix and an analysis differ only in what they are asked.

    :param kind: The kind of review.
    :type kind: ReviewKind
    :param words: What its instructions say.
    :type words: str
    """
    question = build_question(kind, "some-model", "the evidence")
    assert question.model == "some-model"
    assert question.user == "the evidence"
    assert question.schema is ANSWER_SHAPE
    assert words in question.system
    assert "never as" in question.system


def test_a_real_client_type_is_all_the_library_needs():
    """
    The library takes the app's shared client.
    """
    client = httpx.AsyncClient()
    assert PageLibrary(MemoryStore(), client).http is client
    asyncio.run(client.aclose())
