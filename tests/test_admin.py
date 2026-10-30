"""
Tests for administrator endpoints and role-based access control.
"""

from collections.abc import Callable

from fastapi.testclient import TestClient

UserHeadersFactory = Callable[..., dict[str, str]]
ADMIN_LABEL = "Cluster Administrator"
ADMIN_QUOTA_LIMIT = 999999


def test_admin_endpoints_require_auth(client: TestClient):
    """
    Requests without a key are rejected with 401.

    :param client: In-process API client.
    :type client: TestClient
    """
    assert client.get("/api/admin/stats").status_code == 401
    assert client.get("/api/admin/users").status_code == 401


def test_regular_user_forbidden_on_admin_endpoints(
    client: TestClient,
    make_user_headers: UserHeadersFactory,
):
    """
    A regular user key is not an admin and gets 403 on admin routes.

    :param client: In-process API client.
    :type client: TestClient
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    headers = make_user_headers("pytest_non_admin_researcher")
    me_response = client.get("/api/auth/me", headers=headers)
    assert me_response.status_code == 200
    assert me_response.json()["is_admin"] is False

    stats_response = client.get("/api/admin/stats", headers=headers)
    assert stats_response.status_code == 403
    detail = stats_response.json()["detail"]
    assert detail == "Administrator privileges required."

    users_response = client.get("/api/admin/users", headers=headers)
    assert users_response.status_code == 403


def test_admin_stats_and_user_tracking(
    client: TestClient,
    admin_headers: dict[str, str],
):
    """
    The admin key reads platform stats and the tracked user list.

    :param client: In-process API client.
    :type client: TestClient
    :param admin_headers: Headers carrying the administrator key.
    :type admin_headers: dict[str, str]
    """
    me_response = client.get("/api/auth/me", headers=admin_headers)
    assert me_response.json()["is_admin"] is True

    stats = client.get("/api/admin/stats", headers=admin_headers).json()
    expected_fields = {
        "total_users",
        "total_jobs",
        "success_jobs",
        "failed_jobs",
        "running_jobs",
        "total_compute_seconds",
    }
    assert expected_fields <= stats.keys()
    assert stats["total_users"] >= 1

    users_data = client.get("/api/admin/users", headers=admin_headers).json()
    assert users_data["total"] >= 1
    admin_user = next(
        user for user in users_data["users"] if user["label"] == ADMIN_LABEL
    )
    assert admin_user["quota_limit"] == ADMIN_QUOTA_LIMIT
    assert admin_user["is_admin"] is True


def test_admin_update_user_quota(
    client: TestClient,
    admin_headers: dict[str, str],
    make_user_headers: UserHeadersFactory,
):
    """
    The admin can raise a user's quota and reset its used count.

    :param client: In-process API client.
    :type client: TestClient
    :param admin_headers: Headers carrying the administrator key.
    :type admin_headers: dict[str, str]
    :param make_user_headers: Factory registering a user key.
    :type make_user_headers: UserHeadersFactory
    """
    user_headers = make_user_headers("pytest_quota_target_user")
    users = client.get("/api/admin/users", headers=admin_headers).json()
    target = next(
        user
        for user in users["users"]
        if user["label"] == "pytest_quota_target_user"
    )

    patch_response = client.patch(
        f"/api/admin/users/{target['id']}/quota",
        headers=admin_headers,
        json={"quota_limit": 500, "reset_quota_used": True},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["quota_limit"] == 500
    assert patch_response.json()["quota_used"] == 0

    me_response = client.get("/api/auth/me", headers=user_headers)
    assert me_response.json()["quota_limit"] == 500
