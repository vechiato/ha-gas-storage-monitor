"""Lab smoke test. Run inside the container: podman exec -i -e PW=... hass-lab python3 - < lab/smoke.py"""
import asyncio, os
import aiohttp

BASE, CLIENT, PW = "http://localhost:8123", "http://localhost:8123/", os.environ["PW"]


async def token(s):
    r = await s.post(f"{BASE}/api/onboarding/users", json={
        "client_id": CLIENT, "name": "Lab", "username": "lab", "password": PW, "language": "en"})
    if r.status == 200:
        code = (await r.json())["auth_code"]
    else:  # already onboarded: normal login flow
        f = await (await s.post(f"{BASE}/auth/login_flow", json={
            "client_id": CLIENT, "handler": ["homeassistant", None], "redirect_uri": CLIENT})).json()
        code = (await (await s.post(f"{BASE}/auth/login_flow/{f['flow_id']}", json={
            "username": "lab", "password": PW, "client_id": CLIENT})).json())["result"]
    t = await (await s.post(f"{BASE}/auth/token", data={
        "grant_type": "authorization_code", "code": code, "client_id": CLIENT})).json()
    return t["access_token"]


async def ws_call(s, tok, msg):
    async with s.ws_connect(f"{BASE}/api/websocket") as ws:
        await ws.receive_json()
        await ws.send_json({"type": "auth", "access_token": tok})
        await ws.receive_json()
        await ws.send_json({"id": 1, **msg})
        return await ws.receive_json()


async def main():
    async with aiohttp.ClientSession() as s:
        tok = await token(s)
        h = {"Authorization": f"Bearer {tok}"}
        for step, body in [("core_config", {}), ("analytics", {}),
                           ("integration", {"client_id": CLIENT, "redirect_uri": CLIENT})]:
            await s.post(f"{BASE}/api/onboarding/{step}", json=body, headers=h)

        entries = await (await s.get(f"{BASE}/api/config/config_entries/entry", headers=h)).json()
        entry = next((e for e in entries if e["domain"] == "gas_storage_monitor"), None)
        if not entry:
            f = await (await s.post(f"{BASE}/api/config/config_entries/flow",
                                    json={"handler": "gas_storage_monitor"}, headers=h)).json()
            print("flow step:", f.get("type"), f.get("step_id"), f.get("errors"))
            f = await (await s.post(f"{BASE}/api/config/config_entries/flow/{f['flow_id']}",
                                    json={}, headers=h)).json()
            print("flow result:", f.get("type"), f.get("title"))
            entry = f["result"]
            await asyncio.sleep(5)
        print("entry state:", entry.get("state"))

        states = await (await s.get(f"{BASE}/api/states", headers=h)).json()
        for st in sorted((x for x in states if x["entity_id"].startswith("sensor.gas_storage_monitor")),
                         key=lambda x: x["entity_id"]):
            a = st["attributes"]
            print(f"  {st['entity_id']:50} {st['state']:>12} {a.get('unit_of_measurement', ''):4} "
                  f"dc={a.get('device_class')} gas_day={a.get('gas_day')}")

        async def dash():
            panels = (await ws_call(s, tok, {"type": "get_panels"}))["result"]
            cfg = await ws_call(s, tok, {"type": "lovelace/config", "url_path": "gas-storage"})
            ok = cfg.get("success") and cfg["result"]["views"][0]["title"]
            return "gas-storage" in panels, ok
        print("dashboard (panel, view title):", await dash())

        r = await s.post(f"{BASE}/api/config/config_entries/entry/{entry['entry_id']}/reload", headers=h)
        print("reload:", r.status, await r.json())
        await asyncio.sleep(3)
        print("dashboard after reload:", await dash())

asyncio.run(main())
