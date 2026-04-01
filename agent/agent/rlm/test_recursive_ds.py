import asyncio

import pandas as pd

from agent.rlm.container import ContainersResourceManager


async def agent_1_curation():
    """Agent 1: Fetch data, do initial curation, and pass to Agent 2."""
    print("--- Agent 1: Curation ---")
    
    # Simulate a query result from Grafana (discussed in previous turn)
    data = {
        "timestamp": pd.date_range(start="2024-01-01", periods=5, freq="H"),
        "service": ["auth", "auth", "payment", "payment", "auth"],
        "error_count": [10, 15, 2, 3, 20]
    }
    df = pd.DataFrame(data)
    
    # Get a DS sandbox
    sandbox = ContainersResourceManager.get_container("agent-1", ds=True)
    await sandbox.prepare(["pandas"])
    
    # Upload curated data
    await sandbox.upload_dataframe(df, "curated_data")
    
    # Run some curation script
    curation_script = """
curated_data['is_high_error'] = curated_data['error_count'] > 10
summary = curated_data.groupby('service')['error_count'].sum().reset_index()
print("Curation complete. Summary calculated.")
"""
    await sandbox.execute_code(curation_script)
    
    # Export state for Agent 2
    # Option: Pass the DataFrame itself
    curated_df = await sandbox.export_dataframe("curated_data")
    print(f"Agent 1 finished. Curated DF shape: {curated_df.shape}")
    
    return curated_df

async def agent_2_analysis(input_df: pd.DataFrame):
    """Agent 2: Receive data from Agent 1 and do deeper analysis."""
    print("\n--- Agent 2: Deeper Analysis ---")
    
    # Get a NEW DS sandbox for Agent 2
    sandbox = ContainersResourceManager.get_container("agent-2", ds=True)
    await sandbox.prepare(["pandas", "scipy"])
    
    # Load data from Agent 1
    await sandbox.upload_dataframe(input_df, "input_data")
    
    # Deeper analysis (e.g., statistical anomaly detection)
    analysis_script = """
from scipy import stats
z_scores = stats.zscore(input_data['error_count'])
input_data['z_score'] = z_scores
anomalies = input_data[abs(input_data['z_score']) > 1.5]
print(f"Detected {len(anomalies)} anomalies in the data.")
print(anomalies)
"""
    result = await sandbox.execute_code(analysis_script)
    print("Agent 2 Result:")
    print(result)

async def main():
    # Recursive/Chained execution flow
    curated_data = await agent_1_curation()
    await agent_2_analysis(curated_data)
    
    # Cleanup
    ContainersResourceManager.shutdown_container("agent-1")
    ContainersResourceManager.shutdown_container("agent-2")

if __name__ == "__main__":
    asyncio.run(main())
