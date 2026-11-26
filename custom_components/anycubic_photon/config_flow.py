"""Config flow for the Anycubic Photon integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    DEFAULT_PORT,
    PhotonAuthError,
    PhotonClient,
    PhotonConnectionError,
    PhotonError,
)
from .cloud import AUTH_SLICER, AUTH_WEB, AnycubicCloudClient
from .const import (
    CONF_AUTH_MODE,
    CONF_CONNECTION,
    CONF_PRINTER_ID,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    CONNECTION_CLOUD,
    CONNECTION_LOCAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
    connection_type,
)

LOCAL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=65535)
        ),
    }
)

TOKEN_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))

CLOUD_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_AUTH_MODE, default=AUTH_SLICER): SelectSelector(
            SelectSelectorConfig(
                options=[AUTH_SLICER, AUTH_WEB],
                translation_key="auth_mode",
                mode=SelectSelectorMode.LIST,
            )
        ),
        vol.Required(CONF_TOKEN): TOKEN_SELECTOR,
    }
)


class PhotonConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._cloud_data: dict[str, Any] = {}
        self._printers: dict[str, str] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(step_id="user", menu_options=["local", "cloud"])

    # LAN ---------------------------------------------------------------

    async def async_step_local(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            client = PhotonClient(user_input[CONF_HOST], user_input[CONF_PORT])
            try:
                info = await client.get_sysinfo()
            except PhotonConnectionError:
                errors["base"] = "cannot_connect"
            except PhotonError:
                errors["base"] = "invalid_response"
            else:
                await self.async_set_unique_id(info.serial)
                self._abort_if_unique_id_configured(updates=user_input)
                return self.async_create_entry(
                    title=info.model,
                    data={CONF_CONNECTION: CONNECTION_LOCAL, **user_input},
                )

        return self.async_show_form(
            step_id="local",
            data_schema=self.add_suggested_values_to_schema(LOCAL_SCHEMA, user_input),
            errors=errors,
        )

    # Cloud -------------------------------------------------------------

    async def _cloud_printers(self, auth_mode: str, token: str) -> list[dict]:
        client = AnycubicCloudClient(async_get_clientsession(self.hass), auth_mode, token)
        await client.login()
        return await client.list_printers()

    async def async_step_cloud(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                printers = await self._cloud_printers(
                    user_input[CONF_AUTH_MODE], user_input[CONF_TOKEN]
                )
            except PhotonAuthError:
                errors["base"] = "invalid_auth"
            except PhotonError:
                errors["base"] = "cloud_unreachable"
            else:
                if not printers:
                    errors["base"] = "no_printers"
                else:
                    self._cloud_data = {
                        CONF_CONNECTION: CONNECTION_CLOUD,
                        CONF_AUTH_MODE: user_input[CONF_AUTH_MODE],
                        CONF_TOKEN: user_input[CONF_TOKEN].strip().strip('"'),
                    }
                    self._printers = {
                        str(p.get("id")): str(p.get("name") or p.get("model") or p.get("id"))
                        for p in printers
                        if p.get("id") is not None
                    }
                    if len(self._printers) == 1:
                        return await self._create_cloud_entry(next(iter(self._printers)))
                    return await self.async_step_cloud_printer()

        return self.async_show_form(
            step_id="cloud",
            data_schema=self.add_suggested_values_to_schema(
                CLOUD_SCHEMA, {CONF_AUTH_MODE: (user_input or {}).get(CONF_AUTH_MODE, AUTH_SLICER)}
            ),
            errors=errors,
        )

    async def async_step_cloud_printer(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return await self._create_cloud_entry(user_input[CONF_PRINTER_ID])

        options = [
            SelectOptionDict(value=pid, label=name) for pid, name in self._printers.items()
        ]
        return self.async_show_form(
            step_id="cloud_printer",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PRINTER_ID): SelectSelector(
                        SelectSelectorConfig(options=options, mode=SelectSelectorMode.LIST)
                    )
                }
            ),
        )

    async def _create_cloud_entry(self, printer_id: str) -> ConfigFlowResult:
        await self.async_set_unique_id(f"cloud_{printer_id}")
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=self._printers.get(printer_id, "Anycubic printer"),
            data={**self._cloud_data, CONF_PRINTER_ID: int(printer_id)},
        )

    # Re-login when the cloud token stops working -------------------------

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                printers = await self._cloud_printers(
                    user_input[CONF_AUTH_MODE], user_input[CONF_TOKEN]
                )
            except PhotonAuthError:
                errors["base"] = "invalid_auth"
            except PhotonError:
                errors["base"] = "cloud_unreachable"
            else:
                ids = {str(p.get("id")) for p in printers}
                if str(entry.data[CONF_PRINTER_ID]) not in ids:
                    errors["base"] = "printer_missing"
                else:
                    return self.async_update_reload_and_abort(
                        entry,
                        data_updates={
                            CONF_AUTH_MODE: user_input[CONF_AUTH_MODE],
                            CONF_TOKEN: user_input[CONF_TOKEN].strip().strip('"'),
                        },
                    )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=self.add_suggested_values_to_schema(
                CLOUD_SCHEMA, {CONF_AUTH_MODE: entry.data.get(CONF_AUTH_MODE, AUTH_SLICER)}
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return PhotonOptionsFlow()


class PhotonOptionsFlow(OptionsFlow):
    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        mode = connection_type(self.config_entry.data)
        current = self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL[mode])
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_INTERVAL, default=current): vol.All(
                        vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL[mode], max=3600)
                    )
                }
            ),
        )
