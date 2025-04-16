#helm show values grafana/loki-stack > loki-values.yaml


#helm upgrade --install loki -f loki-values.yaml -n monitoring --create-namespace grafana/loki-stack
helm upgrade --install loki grafana/loki-stack -n monitoring --create-namespace --set grafana.enabled=true