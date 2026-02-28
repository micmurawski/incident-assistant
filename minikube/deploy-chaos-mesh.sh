helm repo add chaos-mesh https://charts.chaos-mesh.org
helm repo update

# Install Chaos Mesh
helm upgrade --install chaos-mesh chaos-mesh/chaos-mesh \
  -n chaos --create-namespace \
  --version 2.5.1 \
  --wait