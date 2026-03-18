import asyncio

from agent.grafana_client.client import GrafanaClient
from agent.grafana_client.report import build_status_report

data = {
    "grafana_api_token": "glsa_6KhMTkYyTPoSJQGt8LzeOOeT5UsW2xIe_554ea121",
    "grafana_url": "http://ae92c625ca7a942e48622fdfc8a31b9b-1030611872.us-east-1.elb.amazonaws.com",
}

client = GrafanaClient(url=data["grafana_url"], api_key=data["grafana_api_token"])


async def main():

    res = await build_status_report(
        client, namespace="application", apps=["mysql", "shipping"], window="90m"
    )
    print(res)
    #result = fetch_error_logs(client, namespace="application", app="payment", from_time="now-30m", to_time="now")
    #for log in result:
    #    print(log)

if __name__ == "__main__":
    asyncio.run(main())
