# Fault: MySQL Service Selector Mismatch

## Title
MySQL Service selector mismatch

## Description
The `app` label in the Service selector for the `mysql` service in `k8s/manifests/mysql.yaml` was changed from `mysql` to `mysqldb`.

## Symptom
The `mysql` service will not route traffic to the `mysql` pods because the selector does not match the pod labels. Services that depend on MySQL (like `shipping`) will fail to connect to the database, leading to errors when calculating shipping costs or retrieving shipping information. Users will likely see errors during checkout or when viewing shipping details.

## Root cause
The Kubernetes Service uses label selectors to identify which pods to route traffic to. By changing the `app` label in the selector to `mysqldb`, it no longer matches the `app: mysql` label on the MySQL pods. Therefore, the Service has no endpoints and drops all incoming traffic.

## Fix
Revert the `app` label in the Service selector in `k8s/manifests/mysql.yaml` back to `mysql`.

```yaml
  selector:
    service: mysql
    app: mysql