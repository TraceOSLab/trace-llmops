from unittest.mock import MagicMock

import pytest

from pkg.oauth.github_oauth import GithubOAuth


@pytest.mark.parametrize("emails", [[], [{"primary": True, "verified": False, "email": "victim@example.com"}]])
def test_github_cannot_link_unverified_email(monkeypatch, emails):
    responses = [MagicMock(), MagicMock()]
    responses[0].json.return_value = {"id": 42, "login": "tester"}
    responses[1].json.return_value = emails
    monkeypatch.setattr("pkg.oauth.github_oauth.requests.get", MagicMock(side_effect=responses))
    oauth = GithubOAuth("test-client", "test-secret", "https://example.com/callback")
    with pytest.raises(ValueError, match="已验证"):
        oauth.get_user_info("test-token")


def test_github_verified_identity_uses_login_when_name_is_missing(monkeypatch):
    responses = [MagicMock(), MagicMock()]
    responses[0].json.return_value = {"id": 42, "name": None, "login": "tester"}
    responses[1].json.return_value = [{"primary": True, "verified": True, "email": "owner@example.com"}]
    monkeypatch.setattr("pkg.oauth.github_oauth.requests.get", MagicMock(side_effect=responses))
    user = GithubOAuth("test", "secret", "https://example.com").get_user_info("token")
    assert (user.id, user.name, user.email) == ("42", "tester", "owner@example.com")


def test_github_missing_identity_is_rejected():
    with pytest.raises(ValueError):
        GithubOAuth("test", "secret", "https://example.com").transform_user_info({"email": "owner@example.com"})
