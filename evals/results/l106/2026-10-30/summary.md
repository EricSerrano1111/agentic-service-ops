| container | image MB | .venv files | import s (median of 3 / run 1) | T_log s (median / max) | T_listen s (median / max) | cold_cache T_listen s | heaviest direct import (ms, run 1) |
|---|---|---|---|---|---|---|---|
| orchestrator | 275 | 4610 | 1.62 / 2.01 | 2.35 / 3.34 | 2.37 / 3.36 | 4.61 | a2a.client 652 |
| agent-reporting | 288 | 5333 | 2.64 / 2.61 | 3.60 / 3.60 | 3.65 / 3.74 | 7.29 | a2a.server.request_handlers 1147 |
| mcp-incidents | 306 | 2889 | 2.81 / 2.60 | 2.84 / 3.12 | 2.95 / 3.22 | 8.43 | mcp.server.mcpserver 1500 |
| agent-qa | 341 | 5387 | 2.47 / 2.54 | 3.09 / 3.35 | 3.18 / 3.42 | 7.19 | a2a.server.request_handlers 1438 |
| agent-forecast | 288 | 5330 | 2.68 / 3.40 | 3.59 / 3.59 | 3.65 / 3.66 | 7.23 | a2a.server.request_handlers 1712 |
| mcp-volume | 399 | 4236 | 2.53 / 2.58 | 2.85 / 3.36 | 2.94 / 3.46 | 7.95 | mcp.server.mcpserver 1673 |
| gateway | 241 | 2589 | 1.27 / 1.27 | 1.59 / 1.60 | 1.63 / 1.64 | 2.66 | fastapi 632 |
| agent-sentiment | 288 | 5332 | 2.91 / 2.68 | 3.60 / 3.61 | 3.66 / 3.68 | 7.54 | a2a.server.request_handlers 1146 |
| mcp-feedback | 399 | 4232 | 2.41 / 2.45 | 3.10 / 3.34 | 3.20 / 3.44 | 7.46 | mcp.server.mcpserver 1508 |
