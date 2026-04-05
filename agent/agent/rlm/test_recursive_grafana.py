import asyncio

import pandas as pd

from agent.grafana_client import GrafanaClient, GrafanaPandasClient
from agent.rlm.container import ContainersResourceManager

# Connection details
GRAFANA_URL = "http://ae92c625ca7a942e48622fdfc8a31b9b-1030611872.us-east-1.elb.amazonaws.com"
GRAFANA_TOKEN = "glsa_6KhMTkYyTPoSJQGt8LzeOOeT5UsW2xIe_554ea121"

async def step_1_log_curation(pd_client: GrafanaPandasClient):
    """Fetch raw logs and do initial filtering."""
    print("--- Step 1: Fetching & Curating Logs ---")
    
    # 1. Fetch raw logs from Loki
    query = '{namespace="application"} |= "error"'
    try:
        df_raw = pd_client.query_loki(query, from_time="now-1h")
        print(f"Fetched {len(df_raw)} raw log entries.")
    except Exception as e:
        print(f"Failed to fetch logs: {e}")
        return pd.DataFrame()

    if df_raw.empty:
        return df_raw

    # 2. Get Sandbox for Curation
    sandbox = ContainersResourceManager.get_container("curator", ds=True)
    await sandbox.prepare(["pandas"])
    await sandbox.upload_dataframe(df_raw, "raw_logs")

    # 3. Perform curation script
    curation_script = """
import pandas as pd
# Initial filter: identify the most talkative app in the error logs
app_counts = raw_logs['label_app'].value_counts()
top_app = app_counts.index[0] if not app_counts.empty else None

if top_app:
    curated = raw_logs[raw_logs['label_app'] == top_app].copy()
    print(f"Curation complete: {len(curated)} logs for top app '{top_app}' found.")
else:
    curated = pd.DataFrame()
    print("No app labels found in logs.")
"""
    await sandbox.execute_code(curation_script)
    
    # 4. Export for the next agent
    curated_df = await sandbox.export_dataframe("curated")
    return curated_df

async def step_2_deep_analysis(curated_df: pd.DataFrame):
    """Take curated logs and 'fish' for the root cause."""
    print("\n--- Step 2: Deep Analysis (Fishing for Info) ---")
    
    # 1. Get Sandbox for Deep Analysis
    sandbox = ContainersResourceManager.get_container("analyst", ds=True)
    await sandbox.prepare(["pandas"])
    await sandbox.upload_dataframe(curated_df, "target_logs")

    # 2. Advanced Analysis Script
    analysis_script = """
import pandas as pd

# 1. Message Pattern Analysis
target_logs['msg_pattern'] = target_logs['message'].str.replace(r'\\d+', 'N', regex=True).str[:80]
patterns = target_logs.groupby('msg_pattern').size().reset_index(name='count').sort_values('count', ascending=False)

print("Top Error Patterns (Normalized):")
print(patterns.head(5).to_string(index=False))

# 2. Temporal Analysis
target_logs['timestamp'] = pd.to_datetime(target_logs['timestamp'])
target_logs.set_index('timestamp', inplace=True)
timeline = target_logs.resample('1min').size()
print("\\nError Timeline (Minutely):")
print(timeline[timeline > 0].tail(10))
"""
    result = await sandbox.execute_code(analysis_script)
    print("Analysis Result:")
    print(result)

async def main():
    g_client = GrafanaClient(url=GRAFANA_URL, api_key=GRAFANA_TOKEN)
    pd_client = GrafanaPandasClient(g_client)

    try:
        curated_data = await step_1_log_curation(pd_client)
        
        if not curated_data.empty:
            await step_2_deep_analysis(curated_data)
        else:
            print("No curated data available for deep analysis.")

    finally:
        pd_client.close()
        ContainersResourceManager.shutdown_container("curator")
        ContainersResourceManager.shutdown_container("analyst")

if __name__ == "__main__":
    asyncio.run(main())
