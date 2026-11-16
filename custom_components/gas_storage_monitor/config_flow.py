import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, OptionsFlowWithReload
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    EntitySelector, EntitySelectorConfig, SelectSelector, SelectSelectorConfig, SelectSelectorMode,
)

from . import BACKFILL_DAYS, DOMAIN, HISTORY_DAYS


def _schema(weather: str | None, history_days=BACKFILL_DAYS) -> vol.Schema:
    # Optional: any weather entity with a forecast (Pirate Weather, Met Office, Met.no, ...).
    return vol.Schema({
        vol.Optional("weather", description={"suggested_value": weather}):
            EntitySelector(EntitySelectorConfig(domain="weather")),
        vol.Required("history_days", default=str(history_days)): SelectSelector(SelectSelectorConfig(
            options=[str(d) for d in HISTORY_DAYS], mode=SelectSelectorMode.DROPDOWN, translation_key="history_days",
        )),
    })


class GasStorageMonitorFlow(ConfigFlow, domain=DOMAIN):
    """National Gas needs no key. Single instance enforced by manifest."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="Gas Storage Monitor", data={}, options=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema(None))

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlow()


class OptionsFlow(OptionsFlowWithReload):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(step_id="init", data_schema=_schema(
            self.config_entry.options.get("weather"), self.config_entry.options.get("history_days", BACKFILL_DAYS)))
