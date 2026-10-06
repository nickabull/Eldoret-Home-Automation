# Eldoret Chromebook runtime

The Chromebook runtime can be installed as a per-user systemd service.

- `manager.py` checks GitHub for a newer `connector.py` every 30 seconds.
- When `connector.py` changes, the manager restarts the connector automatically.
- Hue credentials remain only in `~/.config/eldoret.env` on the Chromebook (mode 600).
- The service restarts automatically if the connector crashes.

The public repository contains no Hue credentials.


## Eldoret local agent

The connector now includes a deliberately constrained local agent.

- It checks `agent-task.json` on GitHub every 30 seconds.
- Only named tasks in the connector's allow-list can run; arbitrary shell commands are not supported.
- Results are stored locally in `~/eldoret-connector/agent-results.json`.
- The latest result is available at `/api/agent/results`.
- This same mechanism is designed to work unchanged when Eldoret moves to Raspberry Pi.
- Credentials remain local and are never written to `agent-task.json`.
