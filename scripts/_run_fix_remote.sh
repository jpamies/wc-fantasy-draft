#!/bin/bash
POD=$(kubectl get pods -l app=wc-fantasy -o jsonpath='{.items[0].metadata.name}')
echo "POD=$POD"
kubectl cp /tmp/fix_bot_lineups.py $POD:/tmp/fix_bot_lineups.py
kubectl exec $POD -- python3 /tmp/fix_bot_lineups.py
