"""Gas Storage Monitor: national gas storage levels and days of cover."""
from datetime import datetime, time, timedelta
import logging
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from homeassistant.components import frontend
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.components.lovelace.dashboard import LovelaceConfig
from homeassistant.components.recorder.models import StatisticMeanType
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.json import json_bytes, json_fragment
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util, slugify
from homeassistant.util.yaml import load_yaml_dict

from . import api

DOMAIN = "gas_storage_monitor"
PLATFORMS = [Platform.SENSOR]
DASHBOARD_URL = "gas-storage"
_LOGGER = logging.getLogger(__name__)

BACKFILL_DAYS = 90
# key: (unit, recorder unit_class, days after the gas day the value became visible)
# Stock/% publish ~15:30 on the gas day; demand D+1 publishes ~14:00 the next day.
BACKFILL = {
    "stock_gwh": ("GWh", "energy", 0),
    "medium_pct": ("%", "unitless", 0),
    "long_pct": ("%", "unitless", 0),
    "demand_gwh": ("GWh", "energy", 1),
    "days": ("d", "duration", 0),
    "stock_change_gwh": ("GWh", "energy", 0),
    "days_forecast": ("d", "duration", 0),
    # Seasonal demand lines up with actual demand on the chart, so it shares its 1-day shift.
    "normal_gwh": ("GWh", "energy", 1),
    "cold_gwh": ("GWh", "energy", 1),
    "warm_gwh": ("GWh", "energy", 1),
    "temp_delta": ("°C", "temperature", 0),
}


def _pending_backfill(entry: ConfigEntry) -> list[str]:
    """Sensors not backfilled yet; sensors added in later versions get their history too."""
    return [key for key in BACKFILL if key not in entry.data.get("backfilled", [])]


async def _backfill(hass: HomeAssistant, entry: ConfigEntry, session) -> None:
    """Import the last 90 gas days into long-term statistics, once per sensor."""
    todo = _pending_backfill(entry)
    hist = api.history(await api.fetch(session, days=BACKFILL_DAYS))
    reg = er.async_get(hass)
    uk = ZoneInfo("Europe/London")
    now_hour = dt_util.utcnow().replace(minute=0, second=0, microsecond=0)
    for key in todo:
        unit, unit_class, shift = BACKFILL[key]
        if not (entity_id := reg.async_get_entity_id("sensor", DOMAIN, f"{DOMAIN}_{key}")):
            continue
        # one hourly row per gas day at 16:00 UK; daily graphs only need one point.
        # Rows from the install hour on are left to the recorder's own stats.
        stats = [
            {"start": start, "mean": v, "min": v, "max": v}
            for d, v in sorted(hist[key].items())
            if (start := datetime.combine(d + timedelta(days=shift), time(16), uk)) < now_hour
        ]
        async_import_statistics(hass, {
            "source": "recorder", "statistic_id": entity_id, "name": None,
            "unit_of_measurement": unit, "unit_class": unit_class,
            "mean_type": StatisticMeanType.ARITHMETIC, "has_sum": False,
        }, stats)
    done = [*entry.data.get("backfilled", []), *todo]
    hass.config_entries.async_update_entry(entry, data={**entry.data, "backfilled": done})
    _LOGGER.info("Backfilled %s days of statistics for %s", BACKFILL_DAYS, ", ".join(todo))


class _Dashboard(LovelaceConfig):
    """Read-only dashboard built from dashboard.yaml at setup (reload the integration to refresh)."""

    mode = "yaml"

    def __init__(self, hass: HomeAssistant, config: dict) -> None:
        super().__init__(hass, DASHBOARD_URL, {"mode": "yaml"})
        self._config, self._json = config, json_fragment(json_bytes(config))

    async def async_get_info(self) -> dict:
        return {"mode": self.mode, "views": len(self._config["views"])}

    async def async_load(self, force: bool) -> dict:
        return self._config

    async def async_json(self, force: bool) -> json_fragment:
        return self._json


_DEFAULT_ID = re.compile(rf"sensor\.{DOMAIN}_[a-z0-9_]+")


def _entity_ids(hass: HomeAssistant) -> dict[str, str]:
    """Default entity ID -> the entity ID this install actually has, for every sensor that differs."""
    from .sensor import SENSORS  # noqa: PLC0415 - sensor imports DOMAIN from here

    reg = er.async_get(hass)
    ids = {}
    for desc in SENSORS:
        default = f"sensor.{DOMAIN}_{slugify(desc.name)}"
        if (actual := reg.async_get_entity_id("sensor", DOMAIN, f"{DOMAIN}_{desc.key}")) and actual != default:
            ids[default] = actual
    return ids


def _rewrite(node, ids: dict[str, str]):
    """Swap default entity IDs for the real ones anywhere in the config, templates included."""
    if isinstance(node, dict):
        return {k: _rewrite(v, ids) for k, v in node.items()}
    if isinstance(node, list):
        return [_rewrite(v, ids) for v in node]
    if isinstance(node, str):
        return _DEFAULT_ID.sub(lambda m: ids.get(m.group(0), m.group(0)), node)
    return node


def _load_dashboard(weather: str | None, ids: dict[str, str]) -> dict:
    """dashboard.yaml with this install's entity IDs, and `if_weather` cards pointed at the
    chosen weather entity or dropped."""
    config = load_yaml_dict(Path(__file__).parent / "dashboard.yaml")
    for section in config["views"][0]["sections"]:
        cards = []
        for card in section["cards"]:
            if card.pop("if_weather", False):
                if not weather:
                    continue
                if "entity" in card:
                    card["entity"] = weather
            cards.append(card)
        section["cards"] = cards
    return _rewrite(config, ids)


async def _register_dashboard(hass: HomeAssistant, weather: str | None) -> None:
    # mirrors how lovelace registers its own dashboards; LOVELACE_DATA and LovelaceConfig
    # are internal API, so if a HA update breaks this, only the dashboard is lost.
    # Entity IDs are read at setup: reload the integration after renaming entities.
    config = await hass.async_add_executor_job(_load_dashboard, weather, _entity_ids(hass))
    hass.data[LOVELACE_DATA].dashboards[DASHBOARD_URL] = _Dashboard(hass, config)
    frontend.async_register_built_in_panel(
        hass, "lovelace", frontend_url_path=DASHBOARD_URL, sidebar_title="Gas Storage",
        sidebar_icon="mdi:gas-cylinder", require_admin=False, config={"mode": "yaml"},
    )


def _remove_dashboard(hass: HomeAssistant) -> None:
    frontend.async_remove_panel(hass, DASHBOARD_URL, warn_if_unknown=False)
    if data := hass.data.get(LOVELACE_DATA):
        data.dashboards.pop(DASHBOARD_URL, None)


async def _update(session):
    return api.parse(await api.fetch(session))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = async_get_clientsession(hass)
    entry.runtime_data = coordinator = DataUpdateCoordinator(
        hass,
        logging.getLogger(__name__),
        config_entry=entry,
        name=DOMAIN,
        update_method=lambda: _update(session),
        # data lands once a day ~15:30; hourly polling = one small POST/h, picks it up within the hour
        update_interval=timedelta(hours=1),
    )
    await coordinator.async_config_entry_first_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    try:
        await _register_dashboard(hass, entry.options.get("weather"))
    except Exception:  # noqa: BLE001 - sensors must keep working if HA internals change
        _LOGGER.exception("Could not register Gas Storage dashboard")
    if _pending_backfill(entry):
        entry.async_create_background_task(hass, _backfill_safe(hass, entry, session), "gas_storage_backfill")
    return True


async def _backfill_safe(hass, entry, session):
    try:
        await _backfill(hass, entry, session)
    except Exception:  # noqa: BLE001 - history is a nice-to-have; retried on next setup
        _LOGGER.exception("Could not backfill gas storage history")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    _remove_dashboard(hass)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
