"""
Labs, from the owner to a user: who may see and run which workflow, and
who may change that.
"""

import asyncio
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.api.dependencies import BROWSER_ONLY_MESSAGE
from app.core.security import API_KEY_HEADER
from app.models.job import Job
from app.models.user import Role, User
from app.sign_in.refusals import SignInProblem
from tests.browser import (
    MY_ACCOUNT,
    OWN_PAGE,
    OWNER,
    problem_in,
    sign_in,
)
from tests.fake_google import Account, FakeGoogle

LABS = "/api/labs"
TASKS = "/api/task-definitions"
TEMPLATES = "/api/pipeline-templates"
WORKFLOWS = "/api/workflows"
SUBMIT = "/api/jobs/submit"
SUBMIT_PIPELINE = "/api/jobs/pipeline/submit"
KEYS = "/api/auth/me/keys"
# The fixture catalog's workflows: one holds two tasks and their
# pipeline, the other a task of its own.
CHAIN = "toy_chain"
OTHER = "toy_other"
OPT = "toy_opt"
NETWORK = "toy_network"
SOLO = "toy_solo"
DEMO = "toy_demo"


def fresh_account(prefix: str = "ada") -> Account:
    """
    An account nobody has used yet.

    :param prefix: How its address starts.
    :type prefix: str
    :return: The account.
    :rtype: Account
    """
    return Account(f"{prefix}{uuid.uuid4().hex[:8]}@lab.ac.in")


def become(client: TestClient, google: FakeGoogle, account: Account) -> None:
    """
    Sign this browser in as someone else, who must get in.

    :param client: In-process API client, the browser.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    :param account: Who signs in.
    :type account: Account
    """
    client.cookies.clear()
    assert problem_in(sign_in(client, google, account)) is None


def new_lab(
    client: TestClient,
    google: FakeGoogle,
    workflows: tuple[str, ...] = (OTHER,),
) -> tuple[str, Account]:
    """
    The owner makes a lab holding these workflows, with a new admin.

    :param client: In-process API client, the browser.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    :param workflows: What the lab is given.
    :type workflows: tuple[str, ...]
    :return: The lab's id, and its admin.
    :rtype: tuple[str, Account]
    """
    become(client, google, OWNER)
    admin = fresh_account("pi")
    body = {"name": f"Lab {uuid.uuid4().hex}", "admin_email": admin.email}
    made = client.post(LABS, json=body, headers=OWN_PAGE)
    assert made.status_code == 201
    lab_id = made.json()["id"]
    given = {"workflows": list(workflows)}
    changed = client.patch(f"{LABS}/{lab_id}", json=given, headers=OWN_PAGE)
    assert changed.status_code == 200
    return lab_id, admin


def add_person(client: TestClient, lab_id: str) -> tuple[Account, str]:
    """
    Whoever is signed in adds a new person to a lab.

    :param client: In-process API client, the browser.
    :type client: TestClient
    :param lab_id: The lab.
    :type lab_id: str
    :return: The person's account and id.
    :rtype: tuple[Account, str]
    """
    account = fresh_account()
    body = {"emails": [account.email]}
    added = client.post(f"{LABS}/{lab_id}/people", json=body, headers=OWN_PAGE)
    assert added.status_code == 200
    people = {person["email"]: person for person in added.json()["people"]}
    return account, people[account.email]["id"]


def tick(client: TestClient, lab_id: str, person_id: str, *names: str):
    """
    Whoever is signed in ticks these workflows for someone.

    :param client: In-process API client, the browser.
    :type client: TestClient
    :param lab_id: The lab.
    :type lab_id: str
    :param person_id: The person.
    :type person_id: str
    :param names: The workflows.
    :type names: str
    :return: The answer.
    :rtype: httpx.Response
    """
    return client.patch(
        f"{LABS}/{lab_id}/people/{person_id}",
        json={"workflows": list(names)},
        headers=OWN_PAGE,
    )


def ids_at(client: TestClient, path: str) -> list[str]:
    """
    The ids of what a list shows the one signed in.

    :param client: In-process API client, the browser.
    :type client: TestClient
    :param path: The list.
    :type path: str
    :return: Ids, in order.
    :rtype: list[str]
    """
    return [item["id"] for item in client.get(path).json()]


def test_workflows_pass_from_the_owner_through_the_admin_to_a_user(
    client: TestClient, google: FakeGoogle
):
    """
    The owner gives a lab a workflow and names its admin, who can then
    sign in and add a user. The user sees nothing until the admin ticks
    it for them, and then only that.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    lab_id, admin = new_lab(client, google, (OTHER,))

    become(client, google, admin)
    assert client.get(MY_ACCOUNT).json()["role"] == Role.ADMIN
    assert client.get(MY_ACCOUNT).json()["lab_id"] == lab_id
    assert ids_at(client, TASKS) == [SOLO]
    lab = client.get(f"{LABS}/{lab_id}").json()
    assert [item["id"] for item in lab["workflows"]] == [OTHER]
    assert [item["id"] for item in lab["available"]] == [OTHER]
    person, person_id = add_person(client, lab_id)

    become(client, google, person)
    assert client.get(MY_ACCOUNT).json()["role"] == Role.USER
    assert ids_at(client, TASKS) == []
    assert ids_at(client, WORKFLOWS) == []

    become(client, google, admin)
    assert tick(client, lab_id, person_id, OTHER).status_code == 200

    become(client, google, person)
    assert ids_at(client, TASKS) == [SOLO]
    assert ids_at(client, WORKFLOWS) == [OTHER]
    assert ids_at(client, TEMPLATES) == []


def test_a_workflow_brings_its_pipelines(
    client: TestClient, google: FakeGoogle
):
    """
    Someone given a workflow holding a pipeline can open it.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    _, admin = new_lab(client, google, (CHAIN,))
    become(client, google, admin)
    assert ids_at(client, TEMPLATES) == [DEMO]
    assert ids_at(client, TASKS) == [OPT, NETWORK]


def test_the_owner_sees_and_runs_everything(
    client: TestClient, google: FakeGoogle
):
    """
    The owner needs no lab and is given every workflow.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    become(client, google, OWNER)
    assert set(ids_at(client, WORKFLOWS)) == {CHAIN, OTHER}
    assert ids_at(client, TASKS) == [OPT, NETWORK, SOLO]
    body = {
        "script_name": NETWORK,
        "parameters": {"method": "smiles"},
        "inputs": {"reference": ["start.xyz"]},
    }
    assert client.post(SUBMIT, json=body, headers=OWN_PAGE).status_code == 202


def test_a_task_outside_someones_workflows_cannot_run(
    client: TestClient, google: FakeGoogle
):
    """
    A task not ticked for someone is refused however it is asked for: a
    job or a pipeline, from the browser or with their key. What is
    ticked runs.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    lab_id, admin = new_lab(client, google, (OTHER,))
    become(client, google, admin)
    person, person_id = add_person(client, lab_id)
    tick(client, lab_id, person_id, OTHER)
    become(client, google, person)
    key = client.post(KEYS, json={"label": "script"}, headers=OWN_PAGE).json()
    with_key = {API_KEY_HEADER: key["api_key"]}
    other_job = {"script_name": NETWORK, "parameters": {}}
    other_pipeline = {
        "nodes": [{"ui_id": "a", "script_name": NETWORK}],
        "edges": [],
    }

    for headers in (OWN_PAGE, with_key):
        job = client.post(SUBMIT, json=other_job, headers=headers)
        assert job.status_code == 422
        assert job.json()["detail"][0]["loc"] == ["body", "script_name"]
        assert "isn't available" in job.json()["detail"][0]["msg"]
        pipeline = client.post(
            SUBMIT_PIPELINE, json=other_pipeline, headers=headers
        )
        assert pipeline.status_code == 422
    mine = {"script_name": SOLO, "parameters": {}}
    assert client.post(SUBMIT, json=mine, headers=with_key).status_code == 202


def test_taking_a_workflow_from_a_lab_stops_everyone_at_once(
    client: TestClient, google: FakeGoogle
):
    """
    Without the workflow, nobody in the lab sees or runs its tasks,
    admin included. Giving it back restores what was ticked.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    lab_id, admin = new_lab(client, google, (OTHER,))
    become(client, google, admin)
    person, person_id = add_person(client, lab_id)
    tick(client, lab_id, person_id, OTHER)

    become(client, google, OWNER)
    client.patch(f"{LABS}/{lab_id}", json={"workflows": []}, headers=OWN_PAGE)
    for someone in (person, admin):
        become(client, google, someone)
        assert ids_at(client, TASKS) == []
    body = {"script_name": SOLO, "parameters": {}}
    assert client.post(SUBMIT, json=body, headers=OWN_PAGE).status_code == 422

    become(client, google, OWNER)
    given = {"workflows": [OTHER]}
    client.patch(f"{LABS}/{lab_id}", json=given, headers=OWN_PAGE)
    become(client, google, person)
    assert ids_at(client, TASKS) == [SOLO]


def test_an_admin_gives_only_what_the_lab_has(
    client: TestClient, google: FakeGoogle
):
    """
    An admin cannot tick a workflow their lab lacks, nor give the lab
    more, nor list other labs.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    lab_id, admin = new_lab(client, google, (OTHER,))
    become(client, google, admin)
    _, person_id = add_person(client, lab_id)

    refused = tick(client, lab_id, person_id, CHAIN)
    assert refused.status_code == 422
    assert CHAIN in refused.json()["detail"]
    given = {"workflows": [CHAIN]}
    more = client.patch(f"{LABS}/{lab_id}", json=given, headers=OWN_PAGE)
    assert more.status_code == 403
    assert client.get(LABS).status_code == 403
    body = {"name": "Mine", "admin_email": "me@lab.ac.in"}
    assert client.post(LABS, json=body, headers=OWN_PAGE).status_code == 403


def test_only_the_owner_changes_roles_or_removes_an_admin(
    client: TestClient, google: FakeGoogle
):
    """
    An admin cannot make someone an admin or remove an admin, themself
    included; the owner can do both, and a person made admin has all
    the lab's workflows.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    lab_id, admin = new_lab(client, google, (OTHER,))
    become(client, google, admin)
    person, person_id = add_person(client, lab_id)
    people = f"{LABS}/{lab_id}/people"
    own_email = client.get(MY_ACCOUNT).json()["email"]
    made_admin = {"role": "admin"}

    promoted = client.patch(
        f"{people}/{person_id}", json=made_admin, headers=OWN_PAGE
    )
    assert promoted.status_code == 403
    lab = client.get(f"{LABS}/{lab_id}").json()
    (own,) = [item for item in lab["people"] if item["role"] == Role.ADMIN]
    assert own["email"] == own_email
    removed = client.delete(f"{people}/{own['id']}", headers=OWN_PAGE)
    assert removed.status_code == 403

    become(client, google, OWNER)
    change = client.patch(
        f"{people}/{person_id}", json=made_admin, headers=OWN_PAGE
    )
    assert change.status_code == 200
    gone = client.delete(f"{people}/{own['id']}", headers=OWN_PAGE)
    assert gone.status_code == 200
    become(client, google, person)
    assert client.get(MY_ACCOUNT).json()["role"] == Role.ADMIN
    assert ids_at(client, TASKS) == [SOLO]


def test_nobody_outside_a_lab_can_touch_it(
    client: TestClient, google: FakeGoogle
):
    """
    Another lab's admin and a lab's own user get the same 404 as for a
    lab that does not exist; nor can an admin reach someone in another
    lab through their own.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    lab_id, admin = new_lab(client, google)
    become(client, google, admin)
    person, person_id = add_person(client, lab_id)
    other_lab, other_admin = new_lab(client, google)
    people = f"{LABS}/{lab_id}/people"
    body = {"emails": ["new@lab.ac.in"]}

    for outsider in (other_admin, person):
        become(client, google, outsider)
        assert client.get(f"{LABS}/{lab_id}").status_code == 404
        assert (
            client.post(people, json=body, headers=OWN_PAGE).status_code == 404
        )
        assert tick(client, lab_id, person_id).status_code == 404
        gone = client.delete(f"{people}/{person_id}", headers=OWN_PAGE)
        assert gone.status_code == 404

    become(client, google, other_admin)
    assert tick(client, other_lab, person_id).status_code == 404
    across = client.delete(
        f"{LABS}/{other_lab}/people/{person_id}", headers=OWN_PAGE
    )
    assert across.status_code == 404
    assert client.get(f"{LABS}/{uuid.uuid4()}").status_code == 404


def test_someone_elsewhere_cannot_be_added(
    client: TestClient, google: FakeGoogle
):
    """
    An address in another lab, or an owner's, refuses the whole request
    and is named; nobody else in it is added.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    lab_id, admin = new_lab(client, google)
    become(client, google, admin)
    person, _ = add_person(client, lab_id)
    other_lab, other_admin = new_lab(client, google)
    become(client, google, other_admin)
    people = f"{LABS}/{other_lab}/people"
    newcomer = fresh_account()

    for taken in (person.email, OWNER.email):
        body = {"emails": [newcomer.email, taken]}
        refused = client.post(people, json=body, headers=OWN_PAGE)
        assert refused.status_code == 409
        assert taken in refused.json()["detail"]
    client.cookies.clear()
    assert problem_in(sign_in(client, google, newcomer))


def test_addresses_are_kept_as_google_gives_them(
    client: TestClient, google: FakeGoogle
):
    """
    However an address is typed, it is the one that signs in, and
    typing it twice adds one person.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    lab_id, admin = new_lab(client, google)
    become(client, google, admin)
    person = fresh_account()
    body = {"emails": [f"  {person.email.upper()} ", person.email]}
    added = client.post(f"{LABS}/{lab_id}/people", json=body, headers=OWN_PAGE)
    listed = [item["email"] for item in added.json()["people"]]
    assert listed.count(person.email) == 1
    become(client, google, person)


def test_removing_someone_shuts_them_out_but_keeps_their_runs(
    client: TestClient,
    google: FakeGoogle,
    make_session: async_sessionmaker,
):
    """
    Removed, someone is signed out at once, their key stops working and
    they cannot sign in again, but their runs stay, and another lab can
    add them later.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    """
    lab_id, admin = new_lab(client, google)
    become(client, google, admin)
    person, person_id = add_person(client, lab_id)
    tick(client, lab_id, person_id, OTHER)
    become(client, google, person)
    secret = client.post(KEYS, json={}, headers=OWN_PAGE).json()["api_key"]
    with_key = {API_KEY_HEADER: secret}
    job = {"script_name": SOLO, "parameters": {}}
    assert client.post(SUBMIT, json=job, headers=with_key).status_code == 202
    their_cookies = dict(client.cookies)

    become(client, google, admin)
    gone = client.delete(
        f"{LABS}/{lab_id}/people/{person_id}", headers=OWN_PAGE
    )
    assert gone.status_code == 200
    assert person.email not in [item["email"] for item in gone.json()["people"]]

    client.cookies.clear()
    client.cookies.update(their_cookies)
    assert client.get(MY_ACCOUNT).status_code == 401
    client.cookies.clear()
    assert client.get(MY_ACCOUNT, headers=with_key).status_code == 401
    finished = sign_in(client, google, person)
    assert problem_in(finished) == SignInProblem.OUTSIDE
    assert asyncio.run(jobs_of(make_session, person.email)) == 1

    other_lab, other_admin = new_lab(client, google)
    become(client, google, other_admin)
    body = {"emails": [person.email]}
    added = client.post(
        f"{LABS}/{other_lab}/people", json=body, headers=OWN_PAGE
    )
    assert added.status_code == 200
    become(client, google, person)
    assert ids_at(client, TASKS) == []


async def jobs_of(make_session: async_sessionmaker, email: str) -> int:
    """
    How many jobs someone has.

    :param make_session: Session factory.
    :type make_session: async_sessionmaker
    :param email: Their email.
    :type email: str
    :return: The count.
    :rtype: int
    """
    query = (
        select(func.count(Job.id))
        .join(User, User.id == Job.owner_id)
        .where(User.email == email)
    )
    async with make_session() as session:
        return await session.scalar(query)


def test_a_key_cannot_run_a_lab(
    client: TestClient,
    google: FakeGoogle,
    admin_headers: dict[str, str],
):
    """
    Labs change only from a signed-in browser, so a leaked key cannot
    hand out workflows; not even the owner's.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    :param admin_headers: Headers carrying the administrator key.
    :type admin_headers: dict[str, str]
    """
    lab_id, _ = new_lab(client, google)
    client.cookies.clear()
    listing = client.get(LABS, headers=admin_headers)
    assert listing.status_code == 403
    assert listing.json()["detail"] == BROWSER_ONLY_MESSAGE
    body = {"workflows": [CHAIN]}
    changed = client.patch(f"{LABS}/{lab_id}", json=body, headers=admin_headers)
    assert changed.status_code == 403


def test_bad_requests_are_turned_back(client: TestClient, google: FakeGoogle):
    """
    Not an address, a name already taken, or a workflow the catalog
    does not have.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    lab_id, _ = new_lab(client, google)
    become(client, google, OWNER)
    lab_name = client.get(f"{LABS}/{lab_id}").json()["name"]
    people = f"{LABS}/{lab_id}/people"

    for not_an_address in ("ada", "ada@lab", "a b@lab.ac.in", "a,b@lab.ac.in"):
        body = {"emails": [not_an_address]}
        refused = client.post(people, json=body, headers=OWN_PAGE)
        assert refused.status_code == 422
        assert not_an_address in refused.json()["detail"]
    nobody = client.post(people, json={"emails": []}, headers=OWN_PAGE)
    assert nobody.status_code == 422
    body = {"name": lab_name, "admin_email": fresh_account().email}
    assert client.post(LABS, json=body, headers=OWN_PAGE).status_code == 409
    ghost = {"workflows": ["ghost"]}
    unknown = client.patch(f"{LABS}/{lab_id}", json=ghost, headers=OWN_PAGE)
    assert unknown.status_code == 422
    assert "ghost" in unknown.json()["detail"]
    owners = {"role": "owner"}
    (person,) = client.get(f"{LABS}/{lab_id}").json()["people"]
    role = client.patch(
        f"{people}/{person['id']}", json=owners, headers=OWN_PAGE
    )
    assert role.status_code == 422


def test_the_owner_lists_and_renames_labs(
    client: TestClient, google: FakeGoogle
):
    """
    The owner's list names each lab's workflows and counts its people.

    :param client: In-process API client.
    :type client: TestClient
    :param google: The fake Google.
    :type google: FakeGoogle
    """
    lab_id, _ = new_lab(client, google, (OTHER,))
    become(client, google, OWNER)
    add_person(client, lab_id)
    labs = {lab["id"]: lab for lab in client.get(LABS).json()}
    assert labs[lab_id]["people"] == 2
    assert [item["title"] for item in labs[lab_id]["workflows"]] == [
        "Toy other"
    ]
    name = f"Renamed {uuid.uuid4().hex}"
    body = {"name": name}
    renamed = client.patch(f"{LABS}/{lab_id}", json=body, headers=OWN_PAGE)
    assert renamed.json()["name"] == name
    assert [item["id"] for item in renamed.json()["available"]] == [
        CHAIN,
        OTHER,
    ]
