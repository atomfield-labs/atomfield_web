"""
What a model suggests is checked against the catalog before anyone sees
it: a made-up setting or a bad value is flagged, not hidden.
"""

from pathlib import Path

import pytest

from app.ai.prompts import ANSWER_SHAPE, AiAnswer, AiSuggestion
from app.ai.suggestions import NOT_A_SETTING, check_suggestions
from app.catalog.catalog import Catalog

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "catalog.json"
TASK = "toy_opt"
CURRENT = {"charge": 0, "temp": 300.0, "gfn": 2, "optlevel": "normal"}


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    """
    The fixture catalog.

    :return: Catalog with the toy tasks.
    :rtype: Catalog
    """
    return Catalog.from_path(FIXTURE)


def problem_of(
    catalog: Catalog,
    setting: str,
    value: str,
    task: str = TASK,
) -> str | None:
    """
    What the check says about one suggestion.

    :param catalog: The catalog.
    :type catalog: Catalog
    :param setting: The setting.
    :type setting: str
    :param value: The suggested value.
    :type value: str
    :param task: The task.
    :type task: str
    :return: The problem, if any.
    :rtype: str | None
    """
    suggestion = AiSuggestion(setting=setting, value=value, why="because")
    current = CURRENT if task == TASK else {"method": "a"}
    checked = check_suggestions([suggestion], catalog, task, current)
    return checked[0].problem


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("temp", "350.5"),
        ("charge", "1"),
        ("gfnff", "true"),
        ("gfnff", "True"),
        ("optlevel", "tight"),
        ("gfn", "1"),
        ("solvent", "water"),
    ],
)
def test_a_good_value_passes(catalog: Catalog, setting: str, value: str):
    """
    Every kind of setting takes a good value given as text.

    :param catalog: The catalog.
    :type catalog: Catalog
    :param setting: The setting.
    :type setting: str
    :param value: The value.
    :type value: str
    """
    assert problem_of(catalog, setting, value) is None


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("temp", "-5"),
        ("temp", "warm"),
        ("charge", "one"),
        ("optlevel", "extreme"),
        ("gfn", "7"),
    ],
)
def test_a_bad_value_is_flagged(catalog: Catalog, setting: str, value: str):
    """
    Out of range, the wrong kind, or not among the choices.

    :param catalog: The catalog.
    :type catalog: Catalog
    :param setting: The setting.
    :type setting: str
    :param value: The value.
    :type value: str
    """
    problem = problem_of(catalog, setting, value)
    assert problem is not None
    assert problem != NOT_A_SETTING


def test_a_made_up_setting_is_flagged_and_still_shown(catalog: Catalog):
    """
    It stays in the list, so the person sees the model got it wrong.

    :param catalog: The catalog.
    :type catalog: Catalog
    """
    suggestion = AiSuggestion(setting="smearing_x", value="1", why="because")
    checked = check_suggestions([suggestion], catalog, TASK, CURRENT)
    assert checked[0].setting == "smearing_x"
    assert checked[0].problem == NOT_A_SETTING
    assert checked[0].current is None


def test_a_checked_suggestion_carries_what_the_screen_shows(catalog: Catalog):
    """
    The setting's unit and current value come from the catalog and the
    job, not from the model.

    :param catalog: The catalog.
    :type catalog: Catalog
    """
    suggestion = AiSuggestion(setting="temp", value="350", why="because")
    checked = check_suggestions([suggestion], catalog, TASK, CURRENT)[0]
    assert checked.unit == "K"
    assert checked.current == 300.0
    assert checked.value == "350"
    assert checked.why == "because"


def test_a_setting_that_takes_many_values_takes_a_list(catalog: Catalog):
    """
    Separate values, by spaces or commas.

    :param catalog: The catalog.
    :type catalog: Catalog
    """
    assert problem_of(catalog, "tags", "a, b c", "toy_network") is None


def test_the_reply_shape_needs_no_defs_and_allows_nothing_extra():
    """
    Some vendors refuse nested definitions, and strict mode needs every
    field required and no extras, at every level.
    """
    assert "$defs" not in str(ANSWER_SHAPE)
    item = ANSWER_SHAPE["properties"]["suggestions"]["items"]
    for shape in (ANSWER_SHAPE, item):
        assert shape["additionalProperties"] is False
        assert set(shape["required"]) == set(shape["properties"])


def test_the_reply_shape_and_the_model_of_it_agree():
    """
    What the vendors are told to send is what is read back.
    """
    shape = ANSWER_SHAPE["properties"]
    assert set(shape) == set(AiAnswer.model_fields)
    item = shape["suggestions"]["items"]["properties"]
    assert set(item) == set(AiSuggestion.model_fields)
