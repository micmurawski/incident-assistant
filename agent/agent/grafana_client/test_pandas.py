import asyncio

from agent.grafana_client.client import GrafanaClient
from agent.grafana_client.pandas_client import GrafanaPandasClient

# Mock or real credentials (using what was in test.py)
GRAFANA_URL = "http://ae92c625ca7a942e48622fdfc8a31b9b-1030611872.us-east-1.elb.amazonaws.com"
GRAFANA_TOKEN = "glsa_6KhMTkYyTPoSJQGt8LzeOOeT5UsW2xIe_554ea121"

async def main():
    client = GrafanaClient(url=GRAFANA_URL, api_key=GRAFANA_TOKEN)
    pd_client = GrafanaPandasClient(client)
    
    print("Testing Prometheus query...")
    try:
        # Simple query that should return something if cluster is up
        df_prom = await pd_client.query_prometheus('up{job="linkerd-proxy"}', from_time="now-5m", instant=True)
        print("\nPrometheus DataFrame:")
        print(df_prom.head())
        print(f"Columns: {df_prom.columns.tolist()}")
    except Exception as e:
        print(f"Prometheus query failed (maybe cluster is down?): {e}")

    print("\nTesting Loki query...")
    try:
        df_loki = await pd_client.query_loki('{namespace="application"} |= "error"', from_time="now-15m")
        print("\nLoki DataFrame:")
        print(df_loki.head())
        print(f"Columns: {df_loki.columns.tolist()}")
    except Exception as e:
        print(f"Loki query failed: {e}")

    await pd_client.aclose()

if __name__ == "__main__":
    asyncio.run(main())
