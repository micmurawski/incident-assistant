

import asyncio
from agent.grafana_client.client import GrafanaClient
import json
from datetime import datetime, timezone


API_KEY = json.load(open("api_key.json"))
GRAFANA_URL = API_KEY["grafana_url"]
GRAFANA_API_KEY = API_KEY["grafana_api_token"]

grafana_client = GrafanaClient(url=GRAFANA_URL, api_key=GRAFANA_API_KEY)

async def main():
    time_window = "50m"
    from_time = f"now-{time_window}"
    to_time = "now"
    query = '{namespace="application", app="mysql"}'
    logs = await grafana_client.query_loki(query, from_time, to_time)
    print(logs)
    entries = []
    for log in logs:
        msg = log.get("message", None)
        time_utc = datetime.fromtimestamp(log.get("timestamp", 0), tz=timezone.utc).isoformat()
        entries.append(
            {
                "datetime": time_utc,
                "message": msg,
                "labels": log.get("labels", {}),
                "fields": log.get("fields", {}),
            }
        )
        print(entries[-1])
if __name__ == "__main__":
    asyncio.run(main())
