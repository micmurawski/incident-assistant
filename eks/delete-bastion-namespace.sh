for api in $(kubectl api-resources --verbs=list --namespaced -o name); do
  echo "Checking $api in namespace 'bastion'..."
  kubectl get -n bastion $api --ignore-not-found
  kubectl delete $api -n bastion --all
done



kubectl get namespace bastion -o json \
  | jq 'del(.spec.finalizers)' \
  | kubectl replace --raw "/api/v1/namespaces/bastion/finalize" -f -