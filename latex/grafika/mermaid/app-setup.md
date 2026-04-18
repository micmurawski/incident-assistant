graph TD
SRE["SRE Agent"] --> O["Observability Stack"]
subgraph k8s["Kubernetes Cluster"]
subgraph application
robot-shop
end
subgraph bastion
O
load-gen["Load Generator"]
inc-gen["Incident Generator"]
end
robot-shop --> O
load-gen --> robot-shop
inc-gen --> robot-shop
end
SRE --> robot-shop
