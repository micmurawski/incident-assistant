graph LR
    subgraph H["Episodes History"]
        E1["Episode #1"]
        E2["..."]
        E3["Episode #N"]
    end
    C["Mean Agent"]
    I(["Random(Fault Type, Service)"])
    H -->|read| C <-->|read/write| Code[(Code Base)]
    I --> C -->|"generate git.patch and experiment.yaml (optional)"|E4["New Episode"]