import uuid

import pytest
from sqlalchemy import select

from app.models.invite import Invite
from app.models.user import User


async def _register_and_login_owner(client):
    slug = f"acct-{uuid.uuid4().hex[:8]}"
    email = f"owner@{slug}.example"
    password = "owner-password-123"

    register_resp = await client.post(
        "/auth/register",
        json={
            "org_name": "Account Flow Org",
            "org_slug": slug,
            "email": email,
            "password": password,
            "full_name": "Owner User",
        },
    )
    assert register_resp.status_code == 201, register_resp.text

    login_resp = await client.post(
        "/auth/login",
        json={"email": email, "password": password, "org_slug": slug},
    )
    assert login_resp.status_code == 200, login_resp.text
    return {
        "slug": slug,
        "email": email,
        "password": password,
        "headers": {"Authorization": f"Bearer {login_resp.json()['access_token']}"},
    }


def test_invite_email_uses_smtp_and_app_base_url(monkeypatch):
    from app.config import settings
    from app.services import email as email_service

    sent_messages = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            self.host = host
            self.port = port
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def starttls(self):
            raise AssertionError("TLS should not be used for MailHog dev SMTP")

        def login(self, username, password):
            raise AssertionError("Login should not be used without SMTP credentials")

        def send_message(self, message):
            sent_messages.append((self.host, self.port, self.timeout, message))

    monkeypatch.setattr(settings, "SMTP_HOST", "localhost")
    monkeypatch.setattr(settings, "SMTP_PORT", 1025)
    monkeypatch.setattr(settings, "SMTP_USERNAME", "")
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "")
    monkeypatch.setattr(settings, "SMTP_USE_TLS", False)
    monkeypatch.setattr(settings, "APP_BASE_URL", "http://localhost:5173")
    monkeypatch.setattr(email_service.smtplib, "SMTP", FakeSMTP)

    assert email_service.send_invite_email(
        "invitee@example.com",
        "Acme Data",
        "Owner User",
        "invite-token",
        "admin",
    )

    host, port, timeout, message = sent_messages[0]
    assert (host, port, timeout) == ("localhost", 1025, 10)
    assert message["To"] == "invitee@example.com"
    assert message["Subject"] == "You are invited to join Acme Data on DataWatch"
    assert "http://localhost:5173/accept-invite?token=invite-token" in message.as_string()


@pytest.mark.asyncio
async def test_owner_can_invite_and_invitee_can_accept(client, db_session, monkeypatch):
    owner = await _register_and_login_owner(client)
    sent_invites = []
    sent_welcomes = []

    monkeypatch.setattr(
        "app.routers.auth.email_service.send_invite_email",
        lambda to_email, org_name, inviter_name, token, role: sent_invites.append(
            (to_email, org_name, inviter_name, token, role)
        )
        or True,
    )
    monkeypatch.setattr(
        "app.routers.auth.email_service.send_welcome_email",
        lambda to_email, full_name, org_name: sent_welcomes.append((to_email, full_name, org_name)) or True,
    )

    invite_resp = await client.post(
        "/auth/invites",
        json={"email": "new.member@example.com", "role": "member"},
        headers=owner["headers"],
    )

    assert invite_resp.status_code == 200, invite_resp.text
    invite_data = invite_resp.json()
    assert invite_data["email"] == "new.member@example.com"
    assert invite_data["role"] == "member"
    assert sent_invites and sent_invites[0][0] == "new.member@example.com"

    pending_resp = await client.get("/auth/invites", headers=owner["headers"])
    assert pending_resp.status_code == 200, pending_resp.text
    assert [item["email"] for item in pending_resp.json()] == ["new.member@example.com"]

    invite = await db_session.scalar(select(Invite).where(Invite.email == "new.member@example.com"))
    accept_resp = await client.post(
        f"/auth/invites/{invite.token}/accept",
        json={"full_name": "New Member", "password": "member-password-123"},
    )

    assert accept_resp.status_code == 200, accept_resp.text
    assert accept_resp.json()["token_type"] == "bearer"
    assert sent_welcomes == [("new.member@example.com", "New Member", "Account Flow Org")]

    await db_session.refresh(invite)
    assert invite.accepted_at is not None
    user = await db_session.scalar(select(User).where(User.email == "new.member@example.com"))
    assert user is not None
    assert user.role == "member"


@pytest.mark.asyncio
async def test_password_reset_request_and_confirm_updates_password(client, db_session, monkeypatch):
    owner = await _register_and_login_owner(client)
    sent_tokens = []

    monkeypatch.setattr(
        "app.routers.auth.email_service.send_password_reset_email",
        lambda to_email, token: sent_tokens.append((to_email, token)) or True,
    )

    request_resp = await client.post(
        "/auth/reset-password/request",
        json={"email": owner["email"], "org_slug": owner["slug"]},
    )

    assert request_resp.status_code == 200, request_resp.text
    assert sent_tokens and sent_tokens[0][0] == owner["email"]

    confirm_resp = await client.post(
        "/auth/reset-password/confirm",
        json={"token": sent_tokens[0][1], "new_password": "new-owner-password-123"},
    )

    assert confirm_resp.status_code == 200, confirm_resp.text
    assert confirm_resp.json() == {"message": "Password updated"}

    old_login = await client.post(
        "/auth/login",
        json={"email": owner["email"], "password": owner["password"], "org_slug": owner["slug"]},
    )
    assert old_login.status_code == 401

    new_login = await client.post(
        "/auth/login",
        json={"email": owner["email"], "password": "new-owner-password-123", "org_slug": owner["slug"]},
    )
    assert new_login.status_code == 200, new_login.text


@pytest.mark.asyncio
async def test_profile_and_change_password_update_current_user(client):
    owner = await _register_and_login_owner(client)

    profile_resp = await client.patch(
        "/auth/profile",
        json={"full_name": "Updated Owner", "email": "updated-owner@example.com"},
        headers=owner["headers"],
    )

    assert profile_resp.status_code == 200, profile_resp.text
    assert profile_resp.json()["full_name"] == "Updated Owner"
    assert profile_resp.json()["email"] == "updated-owner@example.com"

    short_password_resp = await client.patch(
        "/auth/change-password",
        json={"current_password": owner["password"], "new_password": "short"},
        headers=owner["headers"],
    )
    assert short_password_resp.status_code == 400

    password_resp = await client.patch(
        "/auth/change-password",
        json={"current_password": owner["password"], "new_password": "updated-password-123"},
        headers=owner["headers"],
    )
    assert password_resp.status_code == 200, password_resp.text
    assert password_resp.json() == {"message": "Password updated"}
