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
