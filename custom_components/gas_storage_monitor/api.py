"""National Gas operational data: fetch + parse. No Home Assistant imports, so it runs standalone."""
import datetime as dt

URL = "https://api.nationalgas.com/operationaldata/v1/publications/gasday"
# National Gas returns 403 to non-browser User-Agents.
HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) HomeAssistant-gas_storage_monitor/0.1",
}
IDS = {
    "PUBOBJ330": "stock_kwh",       # Storage, Daily Aggregated Stock level, D+1
    "PUBOB2050": "medium_pct",      # Medium Storage, Actual Stock %
    "PUBOB2046": "long_pct",        # Long Storage (Rough), Actual Stock %
    # Volume, not the energy item PUBOBJ1030: that one leaves out part of demand (its ratio to
    # this swings 6-10 kWh/m3 through the year), while forecasts and seasonal normals are volume.
    "PUBOB637": "demand_mscm",      # Demand Actual, NTS, D+1
    "PUBOB2535": "normal_mscm",     # Demand, NTS, Seasonal Normal Demand
    "PUBOB2066": "cold_mscm",       # Demand - Cold (seasonal)
    "PUBOB2067": "warm_mscm",       # Demand - Warm (seasonal)
    "PUBOB690": "fc1",              # Demand Forecast, NTS, made 1..7 days ahead of the gas day
    "PUBOB36": "fc2",
    "PUBOB39": "fc3",
    "PUBOB42": "fc4",
    "PUBOB45": "fc5",
    "PUBOBJ2341": "fc6",
    "PUBOBJ2342": "fc7",
    "PUBOBJ507": "temp_c",          # Temperature, Forecast, D
    "PUBOBJ510": "temp_normal_c",   # Temperature, Seasonal Normal, D
}
LEADS = range(1, 8)
# fixed GB calorific value, ~39.5 MJ/m3 = 10.97 GWh per mscm; real CV moves ~1%.
# National Gas publishes daily CV if this ever needs to be exact.
GWH_PER_MSCM = 10.97
DAY = dt.timedelta(days=1)


async def fetch(session, days=5, ahead=8, today=None):
    """Raw publications from `days` back to `ahead` days forward. Feed to parse() or history()."""
    today = today or dt.date.today()
    body = {
        "publicationIds": list(IDS),
        "fromDate": str(today - dt.timedelta(days=days)),
        "toDate": str(today + dt.timedelta(days=ahead)),
    }
    import aiohttp  # local import keeps `python3 api.py` self-check runnable without aiohttp

    async with session.post(URL, json=body, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
        resp.raise_for_status()
        return await resp.json()


def _series(raw):
    """Raw series per IDS key: {key: {date: value}}."""
    s = {key: {} for key in IDS.values()}
    for item in raw:
        key = IDS.get(item.get("publicationId"))
        for p in item.get("publications") or [] if key else []:
            if p.get("value") not in (None, ""):
                s[key][dt.date.fromisoformat(p["applicableFor"])] = float(p["value"])
    return s


def _gwh(series):
    return {d: round(v * GWH_PER_MSCM, 1) for d, v in series.items()}


def history(raw):
    """Per-gas-day series for each sensor key: {key: {date: value}}."""
    s = _series(raw)
    stock, demand = s["stock_kwh"], _gwh(s["demand_mscm"])

    def cover_ahead(d):
        # Forecasts made on day d for the next 7 gas days.
        fc = [s[f"fc{k}"][d + k * DAY] for k in LEADS if d + k * DAY in s[f"fc{k}"]]
        return round(stock[d] / 1e6 / (sum(fc) / len(fc) * GWH_PER_MSCM), 2) if fc else None

    return {
        "stock_gwh": {d: round(v / 1e6, 1) for d, v in stock.items()},
        "medium_pct": s["medium_pct"],
        "long_pct": s["long_pct"],
        "demand_gwh": demand,
        "days": {d: round(v / 1e6 / demand[d - DAY], 2) for d, v in stock.items() if demand.get(d - DAY)},
        # stock / average forecast demand of the next 7 days, not a day-by-day drawdown
        "days_forecast": {d: v for d in stock if (v := cover_ahead(d)) is not None},
        # Negative = net withdrawal from storage.
        "stock_change_gwh": {d: round((v - stock[d - DAY]) / 1e6, 1) for d, v in stock.items() if d - DAY in stock},
        "normal_gwh": _gwh(s["normal_mscm"]),
        "cold_gwh": _gwh(s["cold_mscm"]),
        "warm_gwh": _gwh(s["warm_mscm"]),
        "temp_c": s["temp_c"],
        "temp_normal_c": s["temp_normal_c"],
        "temp_delta": {d: round(t - s["temp_normal_c"][d], 1)
                       for d, t in s["temp_c"].items() if d in s["temp_normal_c"]},
    }


def forecast(raw, today):
    """Next 7 gas days: newest available demand forecast for each, with seasonal normal."""
    s = _series(raw)
    rows = []
    for k in LEADS:
        d = today + k * DAY
        # Shortest lead time = most recent forecast for that day.
        v = next((s[f"fc{j}"][d] for j in LEADS if d in s[f"fc{j}"]), None)
        if v is not None:
            normal = s["normal_mscm"].get(d)
            rows.append({"date": d.isoformat(), "demand_gwh": round(v * GWH_PER_MSCM),
                         "normal_gwh": round(normal * GWH_PER_MSCM) if normal is not None else None})
    return rows


def parse(raw, today=None):
    """Latest value per sensor key up to today, plus `<key>_date` for the gas day it applies to."""
    today = today or dt.date.today()
    h = history(raw)
    out = {}
    for key, series in h.items():
        if past := [d for d in series if d <= today]:
            out[key], out[f"{key}_date"] = series[max(past)], max(past)
    # Seasonal demand is compared with actual demand, so it uses the same (previous) gas day.
    for key in ("normal_gwh", "cold_gwh", "warm_gwh"):
        out.pop(key, None), out.pop(f"{key}_date", None)
        if (v := h[key].get(out.get("demand_gwh_date"))) is not None:
            out[key], out[f"{key}_date"] = v, out["demand_gwh_date"]
    if rows := forecast(raw, today):
        out["forecast"] = rows
        out["forecast_gwh"], out["forecast_gwh_date"] = rows[0]["demand_gwh"], dt.date.fromisoformat(rows[0]["date"])
    out["stock_date"] = out.get("stock_gwh_date")  # the "Gas day" sensor
    return out


if __name__ == "__main__":
    p = lambda pid, *rows: {"publicationId": pid, "publications": [  # noqa: E731
        {"applicableFor": d, "value": v} for d, v in rows]}
    sample = [
        p("PUBOBJ330", ("2026-11-09", "11000000000"), ("2026-11-10", "10400000000")),
        p("PUBOB2050", ("2026-11-10", "55.06")),
        p("PUBOB2046", ("2026-11-10", "")),
        p("PUBOB637", ("2026-11-09", "290")),                       # x 10.97 = 3181.3 GWh
        p("PUBOB2535", ("2026-11-09", "250"), ("2026-11-11", "240")),
        p("PUBOB2066", ("2026-11-09", "300")),
        p("PUBOB690", ("2026-11-11", "260")),                       # made 10 Nov for 11 Nov
        p("PUBOB36", ("2026-11-11", "999"), ("2026-11-12", "270")), # older forecast for 11 Nov is ignored
        p("PUBOBJ507", ("2026-11-10", "6.2")),
        p("PUBOBJ510", ("2026-11-10", "7.8")),
    ]
    today = dt.date(2026, 11, 10)
    r = parse(sample, today)
    assert r["stock_gwh"] == 10400.0 and r["stock_date"] == today, r
    assert r["medium_pct"] == 55.06 and "long_pct" not in r, r
    assert r["demand_gwh"] == 3181.3 and r["days"] == round(10400 / 3181.3, 2), r
    assert r["stock_change_gwh"] == -600.0 and r["days_date"] == today, r
    assert r["normal_gwh"] == 2742.5 and r["normal_gwh_date"] == dt.date(2026, 11, 9), r
    assert r["cold_gwh"] == 3291.0 and "warm_gwh" not in r, r
    assert r["forecast"] == [{"date": "2026-11-11", "demand_gwh": 2852, "normal_gwh": 2633},
                             {"date": "2026-11-12", "demand_gwh": 2962, "normal_gwh": None}], r
    assert r["forecast_gwh"] == 2852, r
    assert r["days_forecast"] == round(10400 / (265 * 10.97), 2), r  # mean of 260 and 270 mscm
    assert r["temp_delta"] == -1.6 and r["temp_c"] == 6.2, r
    assert parse([], today) == {"stock_date": None}
    h = history(sample)
    assert list(h["days"]) == [today], h  # 9 Nov stock has no 8 Nov demand
    print("ok")
