graph TD

IC["Incident Commander"] --> CA["Coder Agent"]
IC --> MA["Monitoring Agent"]
IC --> DA["DevOps Agent"]

subgraph L1["L = 1"]
CA
MA
DA
end

CA -.-> CA2
CA -.-> MA2
CA -.-> DA2

MA -.-> CA2
MA -.-> MA2
MA -.-> DA2


DA -.-> CA2
DA -.-> MA2
DA -.-> DA2

subgraph L2["L = 2"]
CA2["Coder Agent"]
MA2["Monitoring Agent"]
DA2["DevOps Agent"]
end