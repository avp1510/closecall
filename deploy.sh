#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_NAME="closecall"
APP_PORT="8080"

mapfile -t TEAM_CONFIGS < <(find /config -maxdepth 1 -type f -name '*.config' | sort)
if (( ${#TEAM_CONFIGS[@]} != 1 )); then
  echo "Expected exactly one /config/*.config file on the workshop VM." >&2
  exit 1
fi

TEAM_CONFIG="${TEAM_CONFIGS[0]}"
TEAM_USERNAME="$(grep '^USERNAME=' "$TEAM_CONFIG" | cut -d= -f2-)"
INGRESS_URL="$(grep '^INGRESS_URL=' "$TEAM_CONFIG" | cut -d= -f2-)"
TEAM_PASSWORD="$(grep '^PASSWORD=' "$TEAM_CONFIG" | cut -d= -f2-)"
NS="$TEAM_USERNAME"
TEAM_N="${TEAM_USERNAME#team-}"
APP_HOST="video-lab-team-${TEAM_N}.cosmos.vastdata.com"
export KUBECONFIG="/config/${NS}-k8s.yaml"

for value in TEAM_USERNAME INGRESS_URL TEAM_PASSWORD; do
  if [[ -z "${!value}" ]]; then
    echo "$value is missing from $TEAM_CONFIG" >&2
    exit 1
  fi
done

kubectl cluster-info >/dev/null

kubectl -n "$NS" create configmap "${APP_NAME}-code" \
  --from-file=main.py="$ROOT/main.py" \
  --from-file=index.html="$ROOT/public/index.html" \
  --from-file=app.js="$ROOT/public/app.js" \
  --from-file=styles.css="$ROOT/public/styles.css" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n "$NS" create secret generic "${APP_NAME}-vss-creds" \
  --from-literal=VSS_URL="$INGRESS_URL" \
  --from-literal=VSS_USERNAME="$TEAM_USERNAME" \
  --from-literal=VSS_PASSWORD="$TEAM_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n "$NS" apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: ${APP_NAME}
  labels:
    app: ${APP_NAME}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: ${APP_NAME}
  template:
    metadata:
      labels:
        app: ${APP_NAME}
    spec:
      containers:
      - name: app
        image: python:3.12-slim
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: ${APP_PORT}
        env:
        - name: PORT
          value: "${APP_PORT}"
        - name: VSS_URL
          valueFrom:
            secretKeyRef:
              name: ${APP_NAME}-vss-creds
              key: VSS_URL
        - name: VSS_USERNAME
          valueFrom:
            secretKeyRef:
              name: ${APP_NAME}-vss-creds
              key: VSS_USERNAME
        - name: VSS_PASSWORD
          valueFrom:
            secretKeyRef:
              name: ${APP_NAME}-vss-creds
              key: VSS_PASSWORD
        workingDir: /code
        command: ["python", "main.py"]
        readinessProbe:
          httpGet:
            path: /health
            port: ${APP_PORT}
          initialDelaySeconds: 3
          periodSeconds: 5
        volumeMounts:
        - name: code
          mountPath: /code/main.py
          subPath: main.py
        - name: code
          mountPath: /code/public/index.html
          subPath: index.html
        - name: code
          mountPath: /code/public/app.js
          subPath: app.js
        - name: code
          mountPath: /code/public/styles.css
          subPath: styles.css
      volumes:
      - name: code
        configMap:
          name: ${APP_NAME}-code
---
apiVersion: v1
kind: Service
metadata:
  name: ${APP_NAME}
  labels:
    app: ${APP_NAME}
spec:
  selector:
    app: ${APP_NAME}
  ports:
  - name: http
    port: 80
    targetPort: ${APP_PORT}
---
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: ${APP_NAME}
  labels:
    app: ${APP_NAME}
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /\$2
spec:
  ingressClassName: nginx
  rules:
  - host: ${APP_HOST}
    http:
      paths:
      - path: /app(/|$)(.*)
        pathType: ImplementationSpecific
        backend:
          service:
            name: ${APP_NAME}
            port:
              number: 80
EOF

kubectl -n "$NS" rollout restart deployment/"$APP_NAME"
kubectl -n "$NS" rollout status deployment/"$APP_NAME" --timeout=180s
kubectl -n "$NS" get pods,service,ingress -l app="$APP_NAME"

echo
echo "CloseCall is deployed at /app for $NS."
echo "Open https://workshop.thecosmoslabs.com and click App."
