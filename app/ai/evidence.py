"""
What a step left, chosen and trimmed for one review. Every trim is
recorded, so the person can see exactly what the model read and what it
didn't. Only files the agent already uploaded are read: script source is
never among them, and big files stay on the cluster.
"""

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from fnmatch import fnmatchcase
from pathlib import Path
from types import MappingProxyType
from typing import Any

from app.agents.schemas import EXECUTION_LOG
from app.ai.pages import PageLibrary, PageParts
from app.catalog.models import ReferencePage, TaskDefinition
from app.models.job import Job
from app.services.job_service import (
    PLOTS_SUFFIX,
    read_job_file,
    uploaded_names,
)
from app.storage.store import ArtifactStore

ENCODING = "utf-8"
LOG_SUFFIX = ".log"
SUMMARY_SUFFIX = "_summary.txt"
INPUT_SUFFIXES = frozenset({".in", ".inp", ".win"})
# Text worth reading that a task doesn't name. Coordinates aren't.
OTHER_SUFFIXES = frozenset({".csv", ".dat", ".json", ".out", ".txt", ".wout"})
ALL_OF_IT = "all"
PARTS_OF_IT = "matching parts"
ENDS_SEPARATOR = "\n...\n"
PLOT_POINTS = (100, 50, 25, 10, 5, 2)
LOG_ERROR_LINE = re.compile(
    r"error|fail|abort|killed|not converged|convergence|%%%", re.IGNORECASE
)
WORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]{4,}")
# Words in error lines that say nothing about which setting is at fault.
PLAIN_WORDS = frozenset(
    {
        "aborted",
        "abort",
        "after",
        "error",
        "errors",
        "failed",
        "failure",
        "fatal",
        "routine",
        "stopped",
        "stopping",
        "warning",
        "which",
        "while",
    }
)
MOST_ERROR_WORDS = 12


class ReviewKind(StrEnum):
    """
    What a review is asked to do, which follows from how its step ended.
    """

    FIX = "fix"
    ANALYSIS = "analysis"


class FileGroup(StrEnum):
    """
    The kinds of file a recipe gives room to.
    """

    LOGS = "logs"
    INPUTS = "inputs"
    DECLARED = "declared"
    OTHER = "other"
    PLOTS = "plots"


@dataclass(frozen=True, slots=True)
class Recipe:
    """
    How many characters of each kind a review may read.

    :param groups: File group -> characters, shared among its files.
    :type groups: Mapping[FileGroup, int]
    :param parents: Characters for the summaries of the steps before.
    :type parents: int
    :param pages: Characters for parts of listed pages.
    :type pages: int
    """

    groups: Mapping[FileGroup, int]
    parents: int
    pages: int


RECIPES = MappingProxyType(
    {
        ReviewKind.FIX: Recipe(
            groups=MappingProxyType(
                {
                    FileGroup.LOGS: 30_000,
                    FileGroup.INPUTS: 10_000,
                    FileGroup.DECLARED: 10_000,
                    FileGroup.OTHER: 10_000,
                    FileGroup.PLOTS: 0,
                }
            ),
            parents=4_000,
            pages=15_000,
        ),
        ReviewKind.ANALYSIS: Recipe(
            groups=MappingProxyType(
                {
                    FileGroup.LOGS: 6_000,
                    FileGroup.INPUTS: 6_000,
                    FileGroup.DECLARED: 40_000,
                    FileGroup.OTHER: 6_000,
                    FileGroup.PLOTS: 6_000,
                }
            ),
            parents=4_000,
            pages=10_000,
        ),
    }
)


@dataclass(frozen=True, slots=True)
class EvidencePart:
    """
    One thing the model reads.

    :param name: The file or page.
    :type name: str
    :param shown: How much of it: ``all``, or what was kept.
    :type shown: str
    :param text: The text.
    :type text: str
    """

    name: str
    shown: str
    text: str


@dataclass(frozen=True, slots=True)
class FileLeft:
    """
    A file that stayed on the cluster.

    :param name: Its name.
    :type name: str
    :param size_bytes: Its size.
    :type size_bytes: int
    """

    name: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class Evidence:
    """
    Everything a review reads about a step, beyond its task and settings.

    :param parts: The files and pages, in the order they are given.
    :type parts: list[EvidencePart]
    :param left_behind: Files that stayed on the cluster.
    :type left_behind: list[FileLeft]
    :param unread_pages: Titles of listed pages that couldn't be read.
    :type unread_pages: list[str]
    """

    parts: list[EvidencePart] = field(default_factory=list)
    left_behind: list[FileLeft] = field(default_factory=list)
    unread_pages: list[str] = field(default_factory=list)

    def record(self) -> dict[str, list]:
        """
        What to store about it: what was read, without the text.

        :return: Column values for ``AiReview``.
        :rtype: dict[str, list]
        """
        read = [{"name": part.name, "shown": part.shown} for part in self.parts]
        return {
            "read_parts": read,
            "unread_pages": self.unread_pages,
            "left_behind": [asdict(item) for item in self.left_behind],
        }


def group_of(
    name: str, task: TaskDefinition, inputs: frozenset[str]
) -> FileGroup | None:
    """
    Which kind of file this is.

    :param name: The file.
    :type name: str
    :param task: The job's task, which names its outputs.
    :type task: TaskDefinition
    :param inputs: The files wired into the job.
    :type inputs: frozenset[str]
    :return: Its group; None if a review doesn't read it.
    :rtype: FileGroup | None
    """
    suffix = Path(name).suffix.lower()
    if name.endswith(PLOTS_SUFFIX):
        return FileGroup.PLOTS
    if name.endswith(LOG_SUFFIX):
        return FileGroup.LOGS
    if name in inputs or suffix in INPUT_SUFFIXES:
        return FileGroup.INPUTS
    if any(fnmatchcase(name, port.glob) for port in task.outputs):
        return FileGroup.DECLARED
    return FileGroup.OTHER if suffix in OTHER_SUFFIXES else None


def fair_shares(sizes: Mapping[str, int], budget: int) -> dict[str, int]:
    """
    Share a budget among files: small ones get all they need, and what
    they leave goes to the larger ones.

    :param sizes: File -> its length.
    :type sizes: Mapping[str, int]
    :param budget: Characters to share.
    :type budget: int
    :return: File -> how much of it to keep.
    :rtype: dict[str, int]
    """
    shares = {}
    left = budget
    for index, name in enumerate(sorted(sizes, key=lambda item: sizes[item])):
        share = min(left // (len(sizes) - index), sizes[name])
        shares[name] = share
        left -= share
    return shares


def amount(count: int) -> str:
    """
    A number of characters, as a person reads it.

    :param count: How many.
    :type count: int
    :return: e.g. ``30,000 characters``.
    :rtype: str
    """
    return f"{count:,} characters"


def trimmed(text: str, keep: int, group: FileGroup) -> tuple[str, str]:
    """
    Cut a file down to its share: the end of what grows as it runs, the
    start of an input, and both ends of a table.

    :param text: The file.
    :type text: str
    :param keep: Characters to keep.
    :type keep: int
    :param group: Its group.
    :type group: FileGroup
    :return: (what is kept, how much that is).
    :rtype: tuple[str, str]
    """
    if len(text) <= keep:
        return text, ALL_OF_IT
    if group in (FileGroup.LOGS, FileGroup.OTHER):
        return text[-keep:], f"last {amount(keep)}"
    if group is FileGroup.INPUTS:
        return text[:keep], f"first {amount(keep)}"
    half = keep // 2
    ends = f"{text[:half]}{ENDS_SEPARATOR}{text[-half:]}"
    return ends, f"first and last {amount(half)}"


def thin(values: list, points: int) -> list:
    """
    Keep evenly spaced values of a series, always with its last one.

    :param values: The series.
    :type values: list
    :param points: Most values to keep.
    :type points: int
    :return: The kept values.
    :rtype: list
    """
    if len(values) <= points:
        return values
    step = (len(values) - 1) / (points - 1)
    return [values[round(index * step)] for index in range(points)]


def thin_curve(curve: dict[str, Any], points: int) -> dict[str, Any]:
    """
    A plot's curve with fewer points, and only what says something.

    :param curve: The curve: its name, x, and one line or many in y.
    :type curve: dict[str, Any]
    :param points: Most points per line.
    :type points: int
    :return: The shorter curve.
    :rtype: dict[str, Any]
    """
    lines = curve.get("y") or []
    if lines and not isinstance(lines[0], list):
        lines = [lines]
    return {
        "name": curve.get("name"),
        "x": thin(curve.get("x") or [], points),
        "y": [thin(line, points) for line in lines],
    }


def thin_panel(panel: dict[str, Any], points: int) -> dict[str, Any]:
    """
    A plot's panel with fewer points.

    :param panel: The panel.
    :type panel: dict[str, Any]
    :param points: Most points per line.
    :type points: int
    :return: Its axis names, and its curves or bars.
    :rtype: dict[str, Any]
    """
    shorter = {
        "x": (panel.get("x") or {}).get("label"),
        "y": (panel.get("y") or {}).get("label"),
    }
    if curves := panel.get("curves"):
        shorter["curves"] = [thin_curve(curve, points) for curve in curves]
    if bars := panel.get("bars"):
        shorter["bars"] = bars
    return shorter


def shorter_plots(plots: list[dict], points: int) -> str:
    """
    Plots with at most this many points per line, as compact JSON.

    :param plots: The plots.
    :type plots: list[dict]
    :param points: Most points per line.
    :type points: int
    :return: The plots' titles and panels.
    :rtype: str
    """
    shorter = [
        {
            "title": plot.get("title"),
            "panels": [
                thin_panel(panel, points) for panel in plot.get("panels", [])
            ],
        }
        for plot in plots
    ]
    return json.dumps(shorter, separators=(",", ":"))


def thinned_plots(text: str, keep: int) -> tuple[str, str] | None:
    """
    A step's plots with few enough points to fit: as many as will, from
    100 per line down.

    :param text: The plots file.
    :type text: str
    :param keep: Characters to keep.
    :type keep: int
    :return: (the plots, how much that is); None if none fit or it can't
        be read.
    :rtype: tuple[str, str] | None
    """
    try:
        plots = json.loads(text).get("plots", [])
        for points in PLOT_POINTS:
            rendered = shorter_plots(plots, points)
            if len(rendered) <= keep:
                return rendered, f"up to {points} points per line"
    except (AttributeError, TypeError, ValueError):
        return None
    return None


def error_words(error: str | None, logs: Sequence[str]) -> list[str]:
    """
    The words in a step's error lines that could name what went wrong.

    :param error: The job's error text.
    :type error: str | None
    :param logs: The ends of its logs.
    :type logs: Sequence[str]
    :return: Words, the most recent lines first, at most a few.
    :rtype: list[str]
    """
    lines = [line for text in logs for line in text.splitlines()]
    wrong = [line for line in reversed(lines) if LOG_ERROR_LINE.search(line)]
    found: dict[str, None] = {}
    for line in [error or "", *wrong]:
        for word in WORD.findall(line):
            if word.lower() not in PLAIN_WORDS:
                found.setdefault(word)
    return list(found)[:MOST_ERROR_WORDS]


def page_terms(
    kind: ReviewKind, task: TaskDefinition, job: Job, logs: Sequence[str]
) -> list[str]:
    """
    What to look for in a task's pages. A failure looks for its error
    lines first; either way the step's own settings are worth explaining.

    :param kind: The kind of review.
    :type kind: ReviewKind
    :param task: The job's task.
    :type task: TaskDefinition
    :param job: The job.
    :type job: Job
    :param logs: The ends of its logs.
    :type logs: Sequence[str]
    :return: Terms, most important first.
    :rtype: list[str]
    """
    settings = [spec.name for spec in task.parameters]
    if kind is not ReviewKind.FIX:
        return settings
    return [*error_words(job.error_message, logs), *settings]


def left_on_cluster(job: Job) -> list[FileLeft]:
    """
    The files of a job that stayed on the cluster.

    :param job: The job.
    :type job: Job
    :return: Their names and sizes, largest first.
    :rtype: list[FileLeft]
    """
    left = [
        FileLeft(name=card["path"], size_bytes=card["size_bytes"])
        for card in job.output_files or []
        if not card["uploaded"]
    ]
    return sorted(left, key=lambda item: -item.size_bytes)


def log_order(job: Job, name: str) -> tuple[int, str]:
    """
    Files in the order they are given: the script's own log first, then
    what the command printed.

    :param job: The job.
    :type job: Job
    :param name: A file.
    :type name: str
    :return: Sort key.
    :rtype: tuple[int, str]
    """
    first = [f"{job.script_name}{LOG_SUFFIX}", EXECUTION_LOG]
    return (first.index(name) if name in first else len(first)), name


def plot_parts(texts: Mapping[str, str], budget: int) -> list[EvidencePart]:
    """
    A step's plots, sharing their budget. A plot that can't be made to fit
    is left out, as half a JSON document is no use to anyone.

    :param texts: The plots files: name -> text.
    :type texts: Mapping[str, str]
    :param budget: Their characters.
    :type budget: int
    :return: The parts.
    :rtype: list[EvidencePart]
    """
    share = budget // len(texts)
    shorter = {name: thinned_plots(text, share) for name, text in texts.items()}
    return [
        EvidencePart(name=name, shown=kept[1], text=kept[0])
        for name, kept in shorter.items()
        if kept
    ]


def page_parts(found: PageParts) -> list[EvidencePart]:
    """
    What was read from a task's pages, as parts.

    :param found: The library's answer.
    :type found: PageParts
    :return: One part per page.
    :rtype: list[EvidencePart]
    """
    return [
        EvidencePart(name=title, shown=PARTS_OF_IT, text=text)
        for title, text in found.parts.items()
    ]


class EvidenceCollector:
    """
    Reads what a step left, within a recipe.
    """

    def __init__(self, store: ArtifactStore, library: PageLibrary) -> None:
        """
        :param store: Where uploaded job files are kept.
        :type store: ArtifactStore
        :param library: Reads a task's listed pages.
        :type library: PageLibrary
        """
        self.store = store
        self.library = library

    async def read_files(self, job: Job) -> dict[str, str]:
        """
        Read the job's uploaded files.

        :param job: The job.
        :type job: Job
        :return: Name -> text.
        :rtype: dict[str, str]
        """
        texts = {}
        for name in sorted(uploaded_names(job)):
            data = await read_job_file(self.store, job, name)
            if data:
                texts[name] = data.decode(ENCODING, "ignore")
        return texts

    def group_parts(
        self, texts: Mapping[str, str], group: FileGroup, budget: int
    ) -> list[EvidencePart]:
        """
        One group's files, sharing its budget.

        :param texts: The group's files: name -> text.
        :type texts: Mapping[str, str]
        :param group: The group.
        :type group: FileGroup
        :param budget: Its characters.
        :type budget: int
        :return: The parts.
        :rtype: list[EvidencePart]
        """
        if group is FileGroup.PLOTS:
            return plot_parts(texts, budget)
        sizes = {name: len(text) for name, text in texts.items()}
        shares = fair_shares(sizes, budget)
        parts = []
        for name, text in texts.items():
            kept, shown = trimmed(text, shares[name], group)
            parts.append(EvidencePart(name=name, shown=shown, text=kept))
        return parts

    def file_parts(
        self,
        job: Job,
        task: TaskDefinition,
        texts: Mapping[str, str],
        recipe: Recipe,
    ) -> list[EvidencePart]:
        """
        The job's own files, by group, within the recipe.

        :param job: The job.
        :type job: Job
        :param task: Its task.
        :type task: TaskDefinition
        :param texts: Its files: name -> text.
        :type texts: Mapping[str, str]
        :param recipe: How much of each kind.
        :type recipe: Recipe
        :return: The parts.
        :rtype: list[EvidencePart]
        """
        wired = job.input_files or {}
        inputs = frozenset(name for names in wired.values() for name in names)
        groups = {name: group_of(name, task, inputs) for name in texts}
        ordered = sorted(texts, key=lambda name: log_order(job, name))
        parts = []
        for group, budget in recipe.groups.items():
            members = {
                name: texts[name] for name in ordered if groups[name] == group
            }
            if members and budget:
                parts += self.group_parts(members, group, budget)
        return parts

    async def parent_parts(
        self, parents: Sequence[Job], budget: int
    ) -> list[EvidencePart]:
        """
        The summaries of the steps this one follows.

        :param parents: The jobs before this one.
        :type parents: Sequence[Job]
        :param budget: Characters to share.
        :type budget: int
        :return: The parts, named ``<step>/<file>``.
        :rtype: list[EvidencePart]
        """
        texts = {}
        for parent in parents:
            for name, text in (await self.read_files(parent)).items():
                if name.endswith(SUMMARY_SUFFIX):
                    texts[f"{parent.node_key}/{name}"] = text
        if not texts:
            return []
        return self.group_parts(texts, FileGroup.DECLARED, budget)

    async def collect(
        self,
        job: Job,
        task: TaskDefinition,
        pages: Sequence[ReferencePage],
        parents: Sequence[Job],
        kind: ReviewKind,
    ) -> Evidence:
        """
        Everything one review reads about a step.

        :param job: The job.
        :type job: Job
        :param task: Its task.
        :type task: TaskDefinition
        :param pages: The pages its task lists.
        :type pages: Sequence[ReferencePage]
        :param parents: The jobs before it.
        :type parents: Sequence[Job]
        :param kind: The kind of review.
        :type kind: ReviewKind
        :return: The evidence.
        :rtype: Evidence
        """
        recipe = RECIPES[kind]
        texts = await self.read_files(job)
        own = self.file_parts(job, task, texts, recipe)
        before = await self.parent_parts(parents, recipe.parents)
        logs = [part.text for part in own if part.name.endswith(LOG_SUFFIX)]
        terms = page_terms(kind, task, job, logs)
        found = await self.library.parts_about(pages, terms, recipe.pages)
        return Evidence(
            parts=[*own, *before, *page_parts(found)],
            left_behind=left_on_cluster(job),
            unread_pages=found.unread,
        )
