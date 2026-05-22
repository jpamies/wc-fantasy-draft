#!/bin/bash
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
POD=$(kubectl get pod -n default -l app=wc-fantasy -o jsonpath='{.items[0].metadata.name}')
kubectl exec -n default "$POD" -- sqlite3 /data/fantasy.db "$1"
