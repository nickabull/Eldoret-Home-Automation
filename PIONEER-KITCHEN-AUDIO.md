# Pioneer Kitchen Audio (21 November 2026)

## Hardware and investigation
- Pioneer XC-HM82D-K ("Kitchen Amp"), four ceiling speakers and subwoofer, LG Kitchen TV / Airlite via Digital In.
- Firmware successfully updated from S9784.5032.1005 to S9784.5032.1010 using USB (photo of unit's system information).
- Was rebooting with Ethernet and Wi-Fi on prior firmware; outcome on new wired firmware not yet established.
- Wireless DHCP previously at 10.0.0.78 (MAC 74-5E-1C-90-48-00). **Wired Ethernet IP/MAC not yet confirmed** and may differ.
- TCP 8102 connected; query ?P returned PWR0 (power on) on old firmware. Other status/control commands are based on generic Pioneer 8102 protocol, *not yet validated against XC-HM82D-K*.

## Eldoret integration
- pioneer.html and pioneer.js: dedicated UI, manual refresh, double-tap confirmation in 10s for each changing action.
- connector.py /api/pioneer/status: manual only (queries ?P, ?V, ?M, ?F); no automatic polling, no background retry.
- connector.py /api/pioneer/control: allowlisted actions volume_up(VU), volume_down(VD), mute_on(MO), mute_off(MF), power_on(PO), power_off(PF), source_next(FU); minimum 1.2s between commands, short connection timeouts and no automatic retry. Requires same-origin LAN request.
- Source code for Digital In not yet mapped; do NOT guess an FN code.
- Default PIONEER_HOST=10.0.0.78 can be overridden by environment variable PIONEER_HOST in Bulldog's Eldoret service environment.
- Pages linked from index.html and av.html.
- **No live Bulldog device verification yet.** Test GET /api/pioneer/status after confirming actual wired IP and then single actions with device observed. Standby power-on may need Pioneer Quick Start networking option; leave off until confirmed.
- Do not re-enable Sky Q read polling: SKY_PASSIVE_ISOLATION must remain True.

## Next
1. Check Bulldog has refreshed connector.py; verify GET /api/pioneer/status and its host.
2. Confirm Pioneer wired IP; update PIONEER_HOST if necessary.
3. Confirm ?V/?M/?F returned data on actual unit.
4. Try single volume step with explicit double confirmation and physically observe.
5. Identify HM82-specific Digital In code safely from documentation or observed source changes before enabling direct input selection.
6. Continue stability monitoring with firmware S9784.5032.1010.

## 21 November 2026: validated controls and rotary knob
- User confirmed live Pioneer power status, and both volume step and mute commands operating correctly from Eldoret on wired Ethernet after firmware update.
- Physical Pioneer volume was **17** at ~11:04 UK time: baseline for comparing `?V` readback (may show a padded raw code, not necessarily displayed user scale).
- Mute combined into a single button, red when muted; single-tap controls requested and committed.
- Rotary knob now handles clockwise/anticlockwise drag, one volume step per gesture (12 degree threshold), arrow key support; **not** an absolute volume-set slider.
- Following a successful manual action, UI performs one user-triggered status read to synchronise actual displayed volume; no background polling.
- Confirm displayed code matches the physical receiver's level before mapping a full dial scale. If raw code differs from 17, establish the transformation, do not guess.

## 21 November 2026 ~11:08: repeat reboot and monitoring
- User observed Pioneer spontaneously reboot at approximately **11:07 UK** after firmware S9784.5032.1010. Wired Ethernet had been moved via a PoE switch. This is a **user-observed reboot**, not collected automatically.
- This confirms the previous firmware release did not eliminate the fault; neither Wi-Fi nor wired via PoE switch has conclusively solved it. Root cause not known.
- New built-in ICMP monitor checks 10.0.0.78 every 30 seconds, logs transition only after two consistent samples, storing UTC timestamps in `~/eldoret-connector/pioneer-connectivity.jsonl`. No TCP 8102 commands or automatic discovery; timeline available at GET `/api/pioneer/monitor` and from the Kitchen Audio page.
- **ICMP reachability loss is not proof of a reboot**. If user removes Ethernet intentionally, resulting loss should not be counted as device fault; correlate with reported front-panel shutdowns and equipment power.
- Log starts only when updated connector restarts and user confirms the host matches wired Pioneer IP. If ping is blocked, this monitor is not reliable. No historical 11:07 ping event is retroactively recorded.
- Suggested later: compare router/switch port link flap and Pioneer power behavior, inspect thermal/ventilation and hardware fault.

## 21 November 2026 ~11:14: reduced terminal dependency
- User requested that ChatGPT do more troubleshooting instead of requiring SSH commands and copy/paste.
- Existing allowlisted GitHub-polled agent now supports read-only tasks: `engineering_runtime`, `engineering_pioneer`, `engineering_snapshot`.
- Engineer snapshot includes connector uptime/health and Pioneer status and ping-based connection history; result at `/api/agent/results`.
- `engineering.html` provides local status inspection, last task output, and links from Bulldog and Pioneer pages. No continuous device-control polling.
- `agent-task.json` submitted one user-approved `engineering_snapshot` request, ID `engineering-snapshot-20261121-1114`. This task may fail if it is fetched before Bulldog's updated connector deploys; if so submit a new ID once deployed.
- No SSH, sudo, arbitrary command execution, secret access, restart or repair actions have been granted. Disruptive actions require a separate design with explicit user approvals.
- Sensitive results are never included in the one-way agent relay; a sanitised summary is sent for supported engineering tasks.
- Live operation pending verification via `http://10.0.0.34:8765/engineering.html`.

## 21 November 2026, midday — return to device communication
- Pioneer endpoint `GET /api/pioneer/connection` already existed and checks ping snapshot, TCP 8102 and TCP 80 without sending receiver control commands. UI `pioneer.html` adds a distinct Diagnose connection button and explicit Retry receiver status button. JS `pioneer.js` displays the three kinds of network status and configured IP. Updated URL `http://10.0.0.34:8765/pioneer.html?v=6`.
- The user previously reported a connection refused problem. No live Pioneer TCP results have been received through this chat since this UI change; **do not claim it has reconnected**. Last observed ping to 10.0.0.78 was responding at 11:10, but this does not prove TCP 8102 works. Check receiver actual power and IP if TCP fails.
- Zappi and Ariya page `zappi.html` has paired connection-status boxes and explicitly blank telemetry for battery percent, range, charger power, energy, and timestamps. `GET /api/ariya/status` is currently an honest `configured:false` placeholder with no vehicle polling/actions; `GET /api/zappi/status` remains a similar placeholder. Page: `http://10.0.0.34:8765/zappi.html?v=4`.
- User confirmed car model **Nissan Ariya** with working app location and climate, but battery data missing in official app. We must check whether Nissan API still reports it. European community integration for Ariya at https://github.com/t0mrg/homeassistant-nissanconnect ; its default approach is cached updates with car wake-ups disabled.
- myenergi gateway serial and API key are required, per https://support.myenergi.com/hc/en-gb/articles/5069627351185-How-do-I-get-an-API-key. **Do not request/paste credentials into ChatGPT.** No credentials collected or actual cloud authentication enabled yet. Native service uses Digest authentication; choose a secure local setup route before collecting credentials.
- Preserve `SKY_PASSIVE_ISOLATION = True`, no Sky Q active polling. No Pioneer polling beyond existing 30-second ICMP connectivity log. The Design Centre is paused per user request.

## 21 November 2026, 12:07 — second-connection refusal isolated
- Screenshot from user: manual readback `power: ok · 8ms`, followed by `volume: connection_failed (ConnectionRefusedError) · 13ms`. Ping and a separate TCP port probe had worked. This is **strong evidence of per-connection rate limiting or a receiver-side single-connection limitation**, though not definitive proof of root cause.
- Updated `pioneer_status()` in `connector.py` to open **one bounded TCP session** and send `?P`, `?V`, `?M`, `?F` sequentially, parsing line-terminated replies with a socket file reader. Added `connection_mode: single_socket` to its response and retained per-query status/timing.
- No retry loops and no added background polling; PIONEER control commands remain untouched.
- Commit `de8cf886492ad6c962dd37bd34250df0cce372ba`. **User has not yet tested this protocol change on Bulldog**. If the receiver closes the first session after one command, the new detailed readback may show `no_reply` or `socket_failed` for volume. In that case investigate a short cooldown between separate connections rather than rapid connection churn. Avoid continuously probing the receiver during instability.

## 21 November 2026, approximately 12:08 GMT — user-observed spontaneous reboot
- User reported: **"it has just rebooted"** at approximately **12:08 GMT**. This was an observed physical Pioneer reboot, not merely a ping failure. Network route at this point was previously stated to be via the PoE switch; no confirmation whether topology changed since.
- This event occurred close to the update of the one-socket readback implementation, but **no evidence that the new connector version was loaded or that a query was in progress at the instant of reboot**. Do not ascribe causation. Correlate with ping monitor records if available.
- Known user-observed reboot timestamps today: approximately **11:07 GMT** and **12:08 GMT**, ~61 minutes between reports (not a proven interval or comprehensive count). Preserve all reported events, even if IP remains reachable in passive log.

## 21 November 2026, 12:11 — SINGLE-SOCKET READBACK CONFIRMED WORKING
- User screenshot captured full success at 12:11:00 (21 Nov): **Power On, volume raw code 089, input raw code 59, Not muted**. Each of four reads succeeded: power 8ms; volume 5ms; mute 4ms; input 13ms.
- This validates the manual one-TCP-session strategy for all four queries. Previous immediate per-command reconnect was refused at second (volume) query. Reboot fault is separate and remains unresolved.
- **Do not convert raw volume 089 to a physical displayed number or percentage until verified.** **Do not assign meaning to source 59 without verification.**
- User-confirmed working status data can now underpin Eldoret Design Centre component bindings; no increase in background control polling.

## Volume calibration — 21 November 2026, 12:12 GMT
- At approximately 12:11 the API reported `VOL089` (displayed by Eldoret as raw code `089`). At 12:12 the user confirmed the physical amplifier volume display was **16**.
- First observed calibration point: **raw `089` ↔ physical display `16`**. Do not infer a conversion formula from one sample, and do not assume the value was unchanged if the user adjusted it in the intervening minute. Ask for one adjacent point after a single volume step to establish direction/step size.

## Control verification — 21 November 2026, 12:12–12:13 GMT
- User explicitly confirmed **Mute is working** after restoring the single-TCP-session status readback. This is a verified live control test, independent of the earlier known mute success.
- Physical volume shown as 16 while recent status read returned raw code 089. First provisional calibration only; no conversion coded.

## 21 November 2026, ~12:16 onward — car integrations before further design work
- User agreed to freeze physical Pioneer page design until the Design Centre is completed, and prioritised **car integration first, Design Centre second**. Preserve current functioning Pioneer status and mute controls.
- Implemented read-only myenergi Zappi client in `connector.py` behind `GET /api/zappi/status`. Uses HTTP Digest authentication over HTTPS, bounded requests, a 120-second cache, and only `/cgi-jstatus-Z` telemetry. Uses `director.myenergi.net` for a validated server shard when available, with `s18.myenergi.net` fallback. **No charger commands or schedules**.
- New private key file: `~/.config/eldoret/myenergi.json`, required to be owned by Bulldog user and mode 0600. Created using interactive `setup-myenergi.py` script with masked API key, atomic write and no credential echo; never commit or paste secrets to chat. Setup requires myenergi gateway/hub serial number, *not* Zappi serial if distinct, and myenergi API key. Existing key is not automatically rotated.
- Zappi values on `zappi.html` remain blank unless the API confirms them. Raw `sta,zmo,div,che` are surfaced for calibration if a real response is received; no speculative conversion of power/energy units yet.
- Nissan Ariya: `/api/ariya/status` still returns an explicit unconfigured placeholder, no fake battery values and no climate commands. Auth integration requires separate work; public Home Assistant EU community integration `dan-r/HomeAssistant-NissanConnect` v0.8.2 (stable Sept 2026) updated OneID login after Nissan broke earlier flows in Aug 2026. v0.9.0-beta.1 (28 Oct 2026) exists and adds diagnostics. Investigate compatible integration carefully and use secure local auth; do not copy customer credentials to chat/GitHub.
- No live API authentication has been validated yet; user action to configure gateway serial/key remains. Existing deployed connector must reload latest GitHub changes.

## 21 November 2026, 17:43 — Zappi gateway API authenticated successfully
- User screenshot on Eldoret Charging page explicitly shows **'Live myenergi status received'**. This verifies Bulldog's gateway serial and private API key worked and returned valid JSON. Read-only live status was reached; dashboard's three numeric boxes were initially blank because conversions had not yet been enabled.
- Using documented Zappi API semantics, coded `myenergi_decode_zappi()`: `sta` and `pst` determine charging/paused/complete/cable state; `zmo` gives charging mode (Fast/Eco/Eco+/Stopped); `div` is power in watts (display as kW), `che` is energy added in kWh. Missing keys deliberately remain unknown; retain raw codes for diagnosing discrepancies.
- Updated `zappi.html` to display charging mode and cable state; no controls or schedule changes. Integration revisions: connector `91d2abab522cbdcd8368e743a41e5a01c8b5911d`; page `d3e6d744dbc0123ddb8bdb146e18a5a908f46c42`.
- **Conversions have not yet been visually verified against the actual charger after deployment.** If live state displays unexpected information, examine raw `sta,pst,div,che,zmo` and cross-check with Zappi screen. Zappi cloud data is cached for 120 seconds. Car Ariya Nissan API still unconfigured.

## 21 November 2026, 17:50 — Zappi failed-to-fetch bug identified and patched
- User screenshot showed Car Charging `Status check failed: Failed to fetch` after Zappi decoding update, despite previous successful API authentication.
- Confirmed `myenergi_decode_zappi()` uses `math.isfinite`, but `math` was only imported inside unrelated UniFi helper, not at module scope. This leads to an unhandled `NameError` when real numeric `div` or `che` fields are processed, causing HTTP connection to terminate without a JSON response.
- Fixed by adding global `import math` to `connector.py`; committed `9f4bb2c8917bb2a7afac24241c19e2f616d4b072`. Credentials, cache, read-only mode and Sky isolation unchanged.
- Not yet verified on live Bulldog after its auto-update: user should reload Car Charging and press Refresh both statuses. If error persists, check `/api/zappi/status` locally before troubleshooting credentials.


## 21 November 2026 evening — PSN presence added to Eldoret
- User tested local PS5 discovery from Bulldog: `online=true`, `host_type=PS5`, `host_name=PS5-086`, IP `10.0.0.48`, but `running_app_name` and `running_app_titleid` were null while PlayStation App showed Fortnite.
- User obtained NPSSO secret and stored it privately; **never paste or commit the secret**.
- Created `psn-bridge.py` read-only PSN presence helper using `PSNAWP`: private `~/.config/eldoret/psn.json` mode 0600, interactive masked token entry and local PSN online ID (default Jesse_Dub_Dub); only returns online status, current title, title ID, artwork, platform, timestamp. No friends list or personal activity history ingested.
- `connector.py` starts the private bridge via `~/psn-test/venv/bin/python` on user-facing read requests, caches at least 120 seconds and restricts PSN results to LAN. Existing local PS5 activity collection continues once per minute.
- `av.html` now prefers PSN game/title image and falls back to local discovery. `index.html` Jesse home tile also prefers PSN game. No fake games or artwork if PSN returns none.
- Bulldog setup required **once**, within private terminal:
  `python3 -m venv ~/psn-test/venv && ~/psn-test/venv/bin/python -m pip install PSNAWP`
  `curl -fsSL https://raw.githubusercontent.com/nickabull/Eldoret-Home-Automation/main/psn-bridge.py -o ~/eldoret-connector/psn-bridge.py && chmod 700 ~/eldoret-connector/psn-bridge.py`
  `~/psn-test/venv/bin/python ~/eldoret-connector/psn-bridge.py --setup`
  Then check `http://10.0.0.34:8765/api/playstation/psn` and `av.html`.
- **Not yet installed/configured or live-verified on Bulldog**. PSN privacy may block Jesse's presence when authenticated with a different account. PSNAWP is unofficial and rate limited; avoid frequent calls, no broad friends scraping. Installation should be verified before considering further controls.
