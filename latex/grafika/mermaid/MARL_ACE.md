graph TD

    A["Agent #1 Reflector"]
    A1["Agent #2 Reflector"]
    
    
    subgraph T1["Trajectory of Agent #2"]
       B1[Tought]
       C1[Action]
       D1[Tought]
       E1["Action"]
    end
    
    subgraph T["Trajectory of Agent #1"]
       B[Tought]
       C["assing_task"]
       D[Tought]
       E[Action]
       F[Tought]
       G[...]
    end

    A1 -->|analyze| B1 --> C1 --> D1 --> E1
    A1 --> R1
    E1 -->|respond| C

    R1 --> Cur1["Agent #2 Curator"]-->|curate reflections|N1[(Agent #2 Playbook)]

    C -->|assing task| B1

    A -->|analyze|B --> C --> D --> E --> F --> G
    

    A ---->|relect_on_assignee|R1(["Agent #2 Reflections"])
    A ---->|reflect|R(["Agent #1 Reflections"])
    R --> Cur["Agent #1 Curator"] -->|curate reflections|N[(Agent #1 Playbook)]
    
    