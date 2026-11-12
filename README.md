# Gas Storage Monitor

National gas storage levels and days of cover for Home Assistant.

Data comes from the [National Gas operational data API](https://apideveloper.nationalgas.com/s). You don't need an API key. Built for HA Container. It adds no pip packages and makes no Supervisor calls.

![Gas Storage dashboard](https://raw.githubusercontent.com/vechiato/ha-gas-storage-monitor/main/docs/images/dashboard.png)

## Sensors

All sensors belong to one device, **Gas Storage Monitor**. They're listed here in the order the device page shows them (alphabetical).

The entity IDs below are what you get when the device has no area. Home Assistant builds new entity IDs from area + device + entity name, so if you assign an area during setup (the "Name and assign" step), it adds the area in front: with an area called *Shaft*, `sensor.gas_storage_monitor_stock` becomes `sensor.shaft_gas_storage_monitor_stock`. The dashboard works either way. To avoid the prefix, leave **Area** empty in that step; assigning an area later from the device settings doesn't change the entity IDs. You can also rename the entities afterwards, or remove *Area* under **Settings → System → Entity ID format** before installing (that setting affects every new entity in Home Assistant).

1. **Days of cover** · `sensor.gas_storage_monitor_days_of_cover` · days
   How long the gas in storage would last if storage alone had to meet demand at yesterday's level: *Stock ÷ Demand previous day*. In reality storage only supplies part of UK gas (the rest comes from the North Sea, Norway and LNG imports), so read it as a stress indicator, not as "days until gas runs out".

2. **Days of cover forecast** · `sensor.gas_storage_monitor_days_of_cover_forecast` · days
   The same idea, looking ahead: *Stock ÷ the average forecast demand for the next 7 days*. Lower than Days of cover means demand is expected to rise.

3. **Demand cold** · `sensor.gas_storage_monitor_demand_cold` · GWh
   The demand National Gas plans for on a cold day at this time of year. The upper band on the demand chart.

4. **Demand forecast** · `sensor.gas_storage_monitor_demand_forecast` · GWh
   National Gas's forecast of total demand for tomorrow's gas day. The `forecast` attribute holds the next 7 days (date, forecast demand and seasonal normal), which feeds the dashboard's "Next 7 days" table.

5. **Demand normal** · `sensor.gas_storage_monitor_demand_normal` · GWh
   Seasonal normal demand: what demand would typically be on this date in average weather. Same gas day as Demand previous day, so the two compare directly.

6. **Demand previous day** · `sensor.gas_storage_monitor_demand_previous_day` · GWh
   Actual total demand on the national gas network for the previous gas day: homes and businesses (through the local distribution networks), power stations, large industry and exports. National Gas publishes it the day after.

7. **Demand warm** · `sensor.gas_storage_monitor_demand_warm` · GWh
   The demand expected on a warm day at this time of year. The lower band on the demand chart.

8. **Gas day** · `sensor.gas_storage_monitor_gas_day` · date
   The gas day the storage figures (Stock, Percent full, Stock change) refer to.

9. **Percent full** · `sensor.gas_storage_monitor_percent_full` · %
   How full the medium-range storage sites are: the salt caverns and similar sites that fill and empty several times a year. This is the main measure of UK storage.

10. **Rough percent full** · `sensor.gas_storage_monitor_rough_percent_full` · %
    How full Rough is, the UK's only long-range (seasonal) storage site under the North Sea. It has been close to empty for years, so the dashboard only shows it when it holds gas.

11. **Stock** · `sensor.gas_storage_monitor_stock` · GWh
    Total gas in storage across all sites, as energy.

12. **Stock change** · `sensor.gas_storage_monitor_stock_change` · GWh
    Today's stock minus yesterday's. Negative means gas was taken out of storage (normal in winter); positive means gas was put in.

13. **Temperature vs normal** · `sensor.gas_storage_monitor_temperature_vs_normal` · °C
    National Gas's temperature forecast for today minus the seasonal normal temperature. Negative means colder than usual, which pushes demand up. Attributes `forecast_c` and `normal_c` hold the two temperatures.

Most sensors also have a `gas_day` attribute: the gas day that figure belongs to.

### Terms

- **Gas day:** the gas industry's day, 05:00 to 05:00 UK time.
- **National gas network (NTS):** the high-pressure National Transmission System run by National Gas.
- **GWh:** gigawatt-hours of energy. 1 GWh = 1 million kWh, roughly a year of gas for 80 typical UK homes.
- **mscm:** million standard cubic metres, the unit National Gas uses for demand volumes.

### Where the data comes from

| Sensor | National Gas data item | Published |
|---|---|---|
| Stock | PUBOBJ330 | daily, about 15:30, for the same gas day |
| Percent full / Rough percent full | PUBOB2050 / PUBOB2046 | daily, about 15:30 |
| Demand previous day | PUBOB637 | about 14:00 the next day |
| Demand forecast | PUBOB690, PUBOB36, PUBOB39, PUBOB42, PUBOB45, PUBOBJ2341, PUBOBJ2342 (forecasts made 1 to 7 days ahead) | daily, about 16:00 |
| Demand normal / cold / warm | PUBOB2535 / PUBOB2066 / PUBOB2067 | published for the year ahead |
| Temperature vs normal | PUBOBJ507, PUBOBJ510 | daily |

All demand figures use National Gas's volume data (mscm), converted at a fixed 10.97 GWh per mscm, so actual, forecast and seasonal demand compare like with like. The energy item PUBOBJ1030 is not used: it leaves out part of demand (likely exports and storage injection), so its ratio to volume swings from 6 to 10 through the year.

The integration polls every hour. On first setup it also imports the last 90 days into long-term statistics, so the charts start out full.

## Dashboard

The integration adds a **Gas Storage** dashboard to the sidebar (`/gas-storage`). It's built from `dashboard.yaml` using built-in cards only, so it's read-only in the UI and updates along with the integration. To customise it, copy that YAML into a dashboard of your own.

### Reading the dashboard

Left column, top to bottom:

| On screen | Sensor | How to read it |
|---|---|---|
| Date badge next to "UK storage" | Gas day | Which gas day the storage figures are for |
| **Full** gauge | Percent full | Red below 25 %, amber below 50 %, green above |
| **Days of cover** gauge | Days of cover | Red below 4 days, amber below 7, green above |
| **Stock** tile | Stock | |
| **Change** tile | Stock change | Negative = gas withdrawn since yesterday |
| **Demand** tile | Demand previous day | |
| **Cover ahead** tile | Days of cover forecast | |
| **Tomorrow** tile | Demand forecast | |
| **vs normal temp** tile | Temperature vs normal | Negative = colder than usual |
| **Rough** tile | Rough percent full | Only shown when Rough holds gas |
| **Next 7 days** table | Demand forecast (`forecast` attribute) | Forecast demand per gas day next to the seasonal normal; a big gap above normal means a cold spell is expected |
| Weather card | your weather entity | Only shown if you chose one (see below) |
| **Days of cover** chart | Days of cover, Days of cover forecast | Blue uses yesterday's demand, yellow uses forecast demand; a falling line means storage is being used up faster than demand eases |

Right column, **Last 90 days**:

| Chart | Sensor | How to read it |
|---|---|---|
| **% full** | Percent full | Storage usually fills through summer and autumn and drains through winter |
| **Daily change (GWh)** | Stock change | Bars above zero are injection, below zero are withdrawal |
| **Demand (GWh)** | Demand previous day, normal, cold, warm | Blue is actual demand; yellow is normal; red and green are the cold and warm bands. Blue near red means a cold-weather level of demand |
| **Temperature vs normal (°C)** | Temperature vs normal | Bars below zero are colder-than-normal days; they usually line up with demand rising towards the cold band |

The charts show daily averages from Home Assistant's long-term statistics. A gap means National Gas published no data for those days (for example, the seasonal normal temperature is missing for 1 to 7 October 2026).

It works on phones too:

<img src="https://raw.githubusercontent.com/vechiato/ha-gas-storage-monitor/main/docs/images/dashboard-phone.png" alt="Gas Storage dashboard on a phone" width="320">

### Weather forecast (optional)

During setup, or later under **Configure**, you can choose a weather entity you already have (Pirate Weather, Met Office, Met.no, …). Its daily forecast is then shown on the dashboard next to the demand forecast. Clear the field to hide it.

<img src="https://raw.githubusercontent.com/vechiato/ha-gas-storage-monitor/main/docs/images/setup.png" alt="Weather forecast option" width="480">

## Install

Requires Home Assistant 2025.11 or newer.

**Marketplace** (Settings → Marketplace):

1. Select **Add from link** and paste `https://github.com/vechiato/ha-gas-storage-monitor`.
2. If asked, connect GitHub. This happens once, only on installs that never had HACS, and only reads public data.
3. Open **Gas Storage Monitor**, select **Install**, then **Set up**.
4. In the **Name and assign** step, leave **Area** empty if you want entity IDs without an area prefix (see [Sensors](#sensors)). You can assign an area later from the device settings without changing the entity IDs.

**HACS** (Home Assistant without the Marketplace): add `https://github.com/vechiato/ha-gas-storage-monitor` as a custom repository with category *Integration*, install it, restart Home Assistant, then add **Gas Storage Monitor** under Settings → Devices & services.

**Manual:** copy `custom_components/gas_storage_monitor/` into your `config/custom_components/` folder, restart Home Assistant, then add **Gas Storage Monitor** under Settings → Devices & services.

## Updating

Install the new version from the Marketplace or HACS, then restart Home Assistant. A restart is needed because Home Assistant only loads an integration's code when it starts.

If you rename the integration's entities, or Home Assistant renames them (for example adding the area name when you choose an area during setup), the dashboard follows: reload the integration under Settings → Devices & services → Gas Storage Monitor → ⋮ → Reload.

## Self-check

`python3 custom_components/gas_storage_monitor/api.py` tests the parser against a canned response.

## Development lab

Throwaway HA in Podman. The integration folder is mounted read-only, so restart the container after you change the code.

```sh
mkdir -p lab/config
podman run -d --name hass-lab -p 8123:8123 -e TZ=Europe/London \
  -v "$PWD/lab/config:/config" \
  -v "$PWD/custom_components/gas_storage_monitor:/config/custom_components/gas_storage_monitor:ro" \
  ghcr.io/home-assistant/home-assistant:stable
podman exec -i -e PW=<password> hass-lab python3 - < lab/smoke.py   # onboard, add integration, check sensors + dashboard
podman restart hass-lab                                            # after code changes
```
