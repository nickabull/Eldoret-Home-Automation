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
