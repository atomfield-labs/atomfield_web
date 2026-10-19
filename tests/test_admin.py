"""
Pytest integration tests for Admin endpoints and role-based access control.
"""

import requests

from app.core.config import settings

BASE_URL = "http://localhost:8000"


def test_admin_endpoints_require_auth():
    """Ensure unauthenticated requests are rejected with 401."""
    res_stats = requests.get(f"{BASE_URL}/api/admin/stats")
    assert res_stats.status_code == 401

    res_users = requests.get(f"{BASE_URL}/api/admin/users")
    assert res_users.status_code == 401


def test_regular_user_forbidden_on_admin_endpoints():
    """Ensure regular non-admin user keys receive 403 Forbidden."""
    create_res = requests.post(
        f"{BASE_URL}/api/auth/keys",
        json={"label": "pytest_non_admin_researcher"},
    )
    assert create_res.status_code == 201
    user_key = create_res.json()["api_key"]
    headers = {"X-API-Key": user_key}

    # Verify /api/auth/me returns is_admin: False
    me_res = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["is_admin"] is False

    # Verify admin endpoints return 403
    stats_res = requests.get(f"{BASE_URL}/api/admin/stats", headers=headers)
    assert stats_res.status_code == 403
    assert stats_res.json()["detail"] == "Administrator privileges required."

    users_res = requests.get(f"{BASE_URL}/api/admin/users", headers=headers)
    assert users_res.status_code == 403


def test_admin_stats_and_user_tracking():
    """Verify administrator key successfully fetches platform and user stats."""
    assert settings.ADMIN_API_KEY is not None
    admin_headers = {"X-API-Key": settings.ADMIN_API_KEY}

    # Verify /api/auth/me returns is_admin: True
    me_res = requests.get(f"{BASE_URL}/api/auth/me", headers=admin_headers)
    assert me_res.status_code == 200
    assert me_res.json()["is_admin"] is True

    # Verify /api/admin/stats returns valid schema
    stats_res = requests.get(
        f"{BASE_URL}/api/admin/stats", headers=admin_headers
    )
    assert stats_res.status_code == 200
    stats = stats_res.json()
    assert "total_users" in stats
    assert "total_jobs" in stats
    assert "success_jobs" in stats
    assert "failed_jobs" in stats
    assert "running_jobs" in stats
    assert "total_compute_seconds" in stats
    assert stats["total_users"] >= 1

    # Verify /api/admin/users returns list of users with tracking statistics
    users_res = requests.get(
        f"{BASE_URL}/api/admin/users", headers=admin_headers
    )
    assert users_res.status_code == 200
    users_data = users_res.json()
    assert "users" in users_data
    assert "total" in users_data
    assert users_data["total"] >= 1

    admin_user = next(
        (
            u
            for u in users_data["users"]
            if u["label"] == "Cluster Administrator"
        ),
        None,
    )
    assert admin_user is not None
    assert admin_user["quota_limit"] == 999999


def test_admin_update_user_quota():
    """Verify administrator can adjust quota limit and reset used quota."""
    # Create test user
    create_res = requests.post(
        f"{BASE_URL}/api/auth/keys",
        json={"label": "pytest_quota_target_user"},
    )
    assert create_res.status_code == 201
    user_key = create_res.json()["api_key"]
    admin_headers = {"X-API-Key": settings.ADMIN_API_KEY}

    # Find the newly created user ID
    users_res = requests.get(
        f"{BASE_URL}/api/admin/users", headers=admin_headers
    )
    users = users_res.json()["users"]
    target = next(
        (u for u in users if u["label"] == "pytest_quota_target_user"),
        None,
    )
    assert target is not None
    target_id = target["id"]

    # Update quota via admin endpoint
    patch_res = requests.patch(
        f"{BASE_URL}/api/admin/users/{target_id}/quota",
        headers=admin_headers,
        json={"quota_limit": 500, "reset_quota_used": True},
    )
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert updated["quota_limit"] == 500
    assert updated["quota_used"] == 0

    # Verify user's own /api/auth/me reflects the new quota
    user_headers = {"X-API-Key": user_key}
    me_res = requests.get(f"{BASE_URL}/api/auth/me", headers=user_headers)
    assert me_res.status_code == 200
    assert me_res.json()["quota_limit"] == 500
