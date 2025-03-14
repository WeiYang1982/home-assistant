"""Tests for config flow."""
from unittest.mock import AsyncMock, patch

from homeassistant.components.withings.const import CONF_USE_WEBHOOK, DOMAIN
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_entry_oauth2_flow

from . import setup_integration
from .conftest import CLIENT_ID, USER_ID

from tests.common import MockConfigEntry
from tests.test_util.aiohttp import AiohttpClientMocker
from tests.typing import ClientSessionGenerator


async def test_full_flow(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    current_request_with_host: None,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Check full flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    state = config_entry_oauth2_flow._encode_jwt(
        hass,
        {
            "flow_id": result["flow_id"],
            "redirect_uri": "https://example.com/auth/external/callback",
        },
    )

    assert result["type"] == FlowResultType.EXTERNAL_STEP
    assert result["url"] == (
        "https://account.withings.com/oauth2_user/authorize2?"
        f"response_type=code&client_id={CLIENT_ID}&"
        "redirect_uri=https://example.com/auth/external/callback&"
        f"state={state}"
        "&scope=user.info,user.metrics,user.activity,user.sleepevents"
    )

    client = await hass_client_no_auth()
    resp = await client.get(f"/auth/external/callback?code=abcd&state={state}")
    assert resp.status == 200
    assert resp.headers["content-type"] == "text/html; charset=utf-8"

    aioclient_mock.clear_requests()
    aioclient_mock.post(
        "https://wbsapi.withings.net/v2/oauth2",
        json={
            "body": {
                "refresh_token": "mock-refresh-token",
                "access_token": "mock-access-token",
                "type": "Bearer",
                "expires_in": 60,
                "userid": 600,
            },
        },
    )
    with patch(
        "homeassistant.components.withings.async_setup_entry", return_value=True
    ) as mock_setup:
        result = await hass.config_entries.flow.async_configure(result["flow_id"])

    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    assert len(mock_setup.mock_calls) == 1

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Withings"
    assert "result" in result
    assert result["result"].unique_id == "600"
    assert "token" in result["result"].data
    assert result["result"].data["token"]["access_token"] == "mock-access-token"
    assert result["result"].data["token"]["refresh_token"] == "mock-refresh-token"


async def test_config_non_unique_profile(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    current_request_with_host: None,
    withings: AsyncMock,
    config_entry: MockConfigEntry,
    disable_webhook_delay,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """Test setup a non-unique profile."""
    await setup_integration(hass, config_entry)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    state = config_entry_oauth2_flow._encode_jwt(
        hass,
        {
            "flow_id": result["flow_id"],
            "redirect_uri": "https://example.com/auth/external/callback",
        },
    )

    assert result["type"] == FlowResultType.EXTERNAL_STEP
    assert result["url"] == (
        "https://account.withings.com/oauth2_user/authorize2?"
        f"response_type=code&client_id={CLIENT_ID}&"
        "redirect_uri=https://example.com/auth/external/callback&"
        f"state={state}"
        "&scope=user.info,user.metrics,user.activity,user.sleepevents"
    )

    client = await hass_client_no_auth()
    resp = await client.get(f"/auth/external/callback?code=abcd&state={state}")
    assert resp.status == 200
    assert resp.headers["content-type"] == "text/html; charset=utf-8"

    aioclient_mock.clear_requests()
    aioclient_mock.post(
        "https://wbsapi.withings.net/v2/oauth2",
        json={
            "body": {
                "refresh_token": "mock-refresh-token",
                "access_token": "mock-access-token",
                "type": "Bearer",
                "expires_in": 60,
                "userid": USER_ID,
            },
        },
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"])
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_config_reauth_profile(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    withings: AsyncMock,
    disable_webhook_delay,
    current_request_with_host,
) -> None:
    """Test reauth an existing profile reauthenticates the config entry."""
    await setup_integration(hass, config_entry)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": SOURCE_REAUTH,
            "entry_id": config_entry.entry_id,
        },
        data=config_entry.data,
    )
    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    state = config_entry_oauth2_flow._encode_jwt(
        hass,
        {
            "flow_id": result["flow_id"],
            "redirect_uri": "https://example.com/auth/external/callback",
        },
    )
    assert result["url"] == (
        "https://account.withings.com/oauth2_user/authorize2?"
        f"response_type=code&client_id={CLIENT_ID}&"
        "redirect_uri=https://example.com/auth/external/callback&"
        f"state={state}"
        "&scope=user.info,user.metrics,user.activity,user.sleepevents"
    )
    client = await hass_client_no_auth()
    resp = await client.get(f"/auth/external/callback?code=abcd&state={state}")
    assert resp.status == 200
    assert resp.headers["content-type"] == "text/html; charset=utf-8"

    aioclient_mock.clear_requests()
    aioclient_mock.post(
        "https://wbsapi.withings.net/v2/oauth2",
        json={
            "body": {
                "refresh_token": "mock-refresh-token",
                "access_token": "mock-access-token",
                "type": "Bearer",
                "expires_in": 60,
                "userid": USER_ID,
            },
        },
    )

    result = await hass.config_entries.flow.async_configure(result["flow_id"])
    assert result
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"


async def test_config_reauth_wrong_account(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    withings: AsyncMock,
    disable_webhook_delay,
    current_request_with_host,
) -> None:
    """Test reauth with wrong account."""
    await setup_integration(hass, config_entry)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": SOURCE_REAUTH,
            "entry_id": config_entry.entry_id,
        },
        data=config_entry.data,
    )
    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    state = config_entry_oauth2_flow._encode_jwt(
        hass,
        {
            "flow_id": result["flow_id"],
            "redirect_uri": "https://example.com/auth/external/callback",
        },
    )
    assert result["url"] == (
        "https://account.withings.com/oauth2_user/authorize2?"
        f"response_type=code&client_id={CLIENT_ID}&"
        "redirect_uri=https://example.com/auth/external/callback&"
        f"state={state}"
        "&scope=user.info,user.metrics,user.activity,user.sleepevents"
    )
    client = await hass_client_no_auth()
    resp = await client.get(f"/auth/external/callback?code=abcd&state={state}")
    assert resp.status == 200
    assert resp.headers["content-type"] == "text/html; charset=utf-8"

    aioclient_mock.clear_requests()
    aioclient_mock.post(
        "https://wbsapi.withings.net/v2/oauth2",
        json={
            "body": {
                "refresh_token": "mock-refresh-token",
                "access_token": "mock-access-token",
                "type": "Bearer",
                "expires_in": 60,
                "userid": 12346,
            },
        },
    )

    result = await hass.config_entries.flow.async_configure(result["flow_id"])
    assert result
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "wrong_account"


async def test_options_flow(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    withings: AsyncMock,
    disable_webhook_delay,
    current_request_with_host,
) -> None:
    """Test options flow."""
    await setup_integration(hass, config_entry)

    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_USE_WEBHOOK: True},
    )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"] == {CONF_USE_WEBHOOK: True}
