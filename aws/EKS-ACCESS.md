# EKS access and node health

## "no such host" / "lookup ... eks.amazonaws.com: no such host"

kubectl cannot resolve the EKS API server hostname. Common causes:

### 1. Public endpoint was disabled (most likely if update-kubeconfig just ran)

The EKS control plane endpoint only resolves **inside the cluster VPC** when public access is off. From your laptop it will always fail with "no such host".

**Fix:** Enable the public API endpoint and apply, then refresh kubeconfig:

```bash
cd aws
# main.tf must have: endpoint_public_access = true
terraform apply
./update-kubeconfig.sh
kubectl get nodes
```

The Terraform EKS module variable is `endpoint_public_access` (default is `false`). After `terraform apply`, the cluster endpoint will be reachable from the internet and DNS will resolve.

### 2. Stale kubeconfig or deleted cluster

- **Stale** – Cluster was recreated and the endpoint URL changed. Run `./update-kubeconfig.sh`.
- **Cluster deleted** – Run `terraform apply` in `aws/`, then `./update-kubeconfig.sh`.

### 3. Local DNS / firewall

If the cluster has public access enabled and the hostname still doesn’t resolve, try: `nslookup <endpoint-hostname>` or use another DNS (e.g. 8.8.8.8) or network to rule out blocking.

---

## "Your current IAM principal doesn't have access to Kubernetes objects"

The cluster is configured so the **IAM principal that created the cluster** gets admin access (EKS Access Entries). If you use a different IAM user/role when running `kubectl`, you will get this error.

**Fix:**

1. Use the same AWS identity that ran `terraform apply` (e.g. IAM user `robot`):
   ```bash
   export AWS_PROFILE=robot   # or however you assume that identity
   aws sts get-caller-identity   # should show arn:aws:iam::189429133920:user/robot
   ```

2. Update kubeconfig for that identity:
   ```bash
   ./update-kubeconfig.sh
   # or:
   aws eks update-kubeconfig --name 1-node-default-vpc --region us-east-1
   ```

3. Use the same profile for kubectl:
   ```bash
   kubectl get nodes
   ```

If you need another IAM user or role to have access, add an EKS Access Entry and policy association in Terraform (e.g. `access_entries` and `access_policy_associations` in the EKS module).

---

## Node group "Unhealthy nodes in the kubernetes cluster"

If node groups fail with `NodeCreationFailure: Unhealthy nodes`, try:

1. **Check why nodes are unhealthy**
   - In AWS Console: EKS → your cluster → Compute → Node groups → select the failed group → look at "Node group status" and any events.
   - EC2 → Instances: find the instance(s), check system log (Console output) and that the node security group allows traffic to the EKS control plane.

2. **Subnet tags**
   - EKS expects subnets to be tagged so it can discover them. The Terraform module usually tags subnets it manages; for an existing VPC (`data.aws_subnets.default`) ensure each subnet has:
     - `kubernetes.io/cluster/<cluster_name> = shared` (or `owned`)

3. **Try x86 and a stable K8s version**
   - To rule out ARM/AL2023 issues, temporarily switch the node group to x86 and a well-established version in `main.tf`:
     - `ami_type = "AL2_x86_64_STANDARD"`
     - `instance_types = ["t3.medium"]`
     - `kubernetes_version = "1.31"` (or "1.32")
   - Run `terraform apply`, then if it works you can switch back to ARM/1.33 after confirming.

4. **Recreate failed node groups**
   - After fixing config, taint and replace so Terraform recreates them:
     ```bash
     terraform taint 'module.eks.module.eks_managed_node_group["apps"].aws_eks_node_group.this[0]'
     terraform taint 'module.eks.module.eks_managed_node_group["observability"].aws_eks_node_group.this[0]'
     terraform apply
     ```
