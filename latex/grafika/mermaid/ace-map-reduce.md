%% Styles the first link (index 0)

graph LR


P[("Playbook vN")]
Ref1[("Reflections")]
Agent[("Agent X Metadata")]

P -->|"without points <span style='font-size:30px; line-height:1;'>+</span>"|Agent
Agent-->|"<span style='font-size:30px; line-height:1;'>+</span>"|T1
Agent-->|"<span style='font-size:30px; line-height:1;'>+</span>"|T2
Agent-->|"<span style='font-size:30px; line-height:1;'>+</span>"|T3
Agent-->|"<span style='font-size:30px; line-height:1;'>+</span>"|T4
Agent-->|"<span style='font-size:30px; line-height:1;'>+</span>"|T5
T1[("Task #i+1")] --> R1
T2[("Task #i+2")] --> R2
T3[("Task #i+3")] --> R3
T4[("Task #i+4")] --> R4
T5[("Task #i+5")] --> R5





R1["Relector X"] --> Ref1
R2["Relector X"] --> Ref1
R3["Relector X"] --> Ref1
R4["Relector X"] --> Ref1
R5["Relector X"] --> Ref1


P[("Playbook X vN")]
Ref1[("Reflections")]

C1["Curator X"]
Ref1 --> C1
P[("Playbook X")] -->|with points|C1 -->|ADD\nDELETE\nUPDATE|P 

