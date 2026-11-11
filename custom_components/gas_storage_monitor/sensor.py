from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfEnergy, UnitOfTime
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import DOMAIN

M = SensorStateClass.MEASUREMENT
SENSORS = [
    SensorEntityDescription(key="stock_gwh", name="Stock", native_unit_of_measurement=UnitOfEnergy.GIGA_WATT_HOUR,
                            device_class=SensorDeviceClass.ENERGY_STORAGE, state_class=M,
                            suggested_display_precision=0, icon="mdi:gas-cylinder"),
    SensorEntityDescription(key="medium_pct", name="Percent full", native_unit_of_measurement=PERCENTAGE,
                            state_class=M, suggested_display_precision=1, icon="mdi:gauge"),
    SensorEntityDescription(key="long_pct", name="Rough percent full", native_unit_of_measurement=PERCENTAGE,
                            state_class=M, suggested_display_precision=1, icon="mdi:gauge"),
    # No ENERGY device class: HA expects that to be a cumulative total, this is a daily figure.
    SensorEntityDescription(key="demand_gwh", name="Demand previous day", native_unit_of_measurement="GWh",
                            state_class=M, icon="mdi:fire"),
    # No DURATION device class: the UI would render 3.5 as "3d 12h".
    SensorEntityDescription(key="days", name="Days of cover", native_unit_of_measurement=UnitOfTime.DAYS,
                            state_class=M, suggested_display_precision=1, icon="mdi:calendar-clock"),
    SensorEntityDescription(key="stock_change_gwh", name="Stock change", native_unit_of_measurement="GWh",
                            state_class=M, icon="mdi:delta"),
    SensorEntityDescription(key="days_forecast", name="Days of cover forecast",
                            native_unit_of_measurement=UnitOfTime.DAYS, state_class=M,
                            suggested_display_precision=1, icon="mdi:calendar-arrow-right"),
    SensorEntityDescription(key="normal_gwh", name="Demand normal", native_unit_of_measurement="GWh",
                            state_class=M, suggested_display_precision=0, icon="mdi:fire"),
    SensorEntityDescription(key="cold_gwh", name="Demand cold", native_unit_of_measurement="GWh",
                            state_class=M, suggested_display_precision=0, icon="mdi:snowflake"),
    SensorEntityDescription(key="warm_gwh", name="Demand warm", native_unit_of_measurement="GWh",
                            state_class=M, suggested_display_precision=0, icon="mdi:weather-sunny"),
    SensorEntityDescription(key="forecast_gwh", name="Demand forecast", native_unit_of_measurement="GWh",
                            state_class=M, icon="mdi:crystal-ball"),
    # No TEMPERATURE device class: this is a difference, which °C -> °F conversion would get wrong.
    SensorEntityDescription(key="temp_delta", name="Temperature vs normal", native_unit_of_measurement="°C",
                            state_class=M, suggested_display_precision=1, icon="mdi:thermometer"),
    SensorEntityDescription(key="stock_date", name="Gas day", device_class=SensorDeviceClass.DATE),
]

# Extra attributes per sensor: {sensor key: {attribute: data key}}.
EXTRA = {
    "forecast_gwh": {"forecast": "forecast"},
    "temp_delta": {"forecast_c": "temp_c", "normal_c": "temp_normal_c"},
}


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(GasSensor(entry.runtime_data, d) for d in SENSORS)


class GasSensor(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True
    _attr_attribution = "Data: National Gas Transmission"

    def __init__(self, coordinator, description):
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, DOMAIN)}, name="Gas Storage Monitor",
            manufacturer="National Gas", entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self):
        return self.coordinator.data.get(self.entity_description.key)

    @property
    def extra_state_attributes(self):
        # Gas day each figure applies to: stock/% are day D, demand is D-1.
        data, key = self.coordinator.data, self.entity_description.key
        attrs = {name: data.get(src) for name, src in EXTRA.get(key, {}).items()}
        if day := data.get(f"{key}_date"):
            attrs["gas_day"] = day.isoformat()
        return attrs or None
