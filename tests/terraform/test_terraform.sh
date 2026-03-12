#!/bin/bash
# Terraform OpenStack Provider compatibility test
set -e

KEYSTONE_PORT=35000
NOVA_PORT=38774
NEUTRON_PORT=39696
GLANCE_PORT=39292
CINDER_PORT=38776

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "=== Starting LocalOStack for Terraform test ==="
LOCALOSTACK_KEYSTONE_PORT=$KEYSTONE_PORT \
LOCALOSTACK_NOVA_PORT=$NOVA_PORT \
LOCALOSTACK_NEUTRON_PORT=$NEUTRON_PORT \
LOCALOSTACK_GLANCE_PORT=$GLANCE_PORT \
LOCALOSTACK_CINDER_PORT=$CINDER_PORT \
LOCALOSTACK_HOST=127.0.0.1 \
LOCALOSTACK_ENDPOINT_HOST=localhost \
  uv run localostack &
SERVER_PID=$!

# Wait for Keystone
for i in $(seq 1 30); do
  if curl -sf "http://localhost:$KEYSTONE_PORT/" > /dev/null 2>&1; then
    echo "  LocalOStack ready"
    break
  fi
  sleep 0.5
done

cleanup() {
  echo "=== Cleaning up ==="
  kill $SERVER_PID 2>/dev/null || true
  cd "$SCRIPT_DIR"
  rm -rf .terraform .terraform.lock.hcl terraform.tfstate terraform.tfstate.backup 2>/dev/null || true
}
trap cleanup EXIT

cd "$SCRIPT_DIR"

echo "=== terraform init ==="
terraform init -no-color

echo "=== terraform apply ==="
terraform apply \
  -auto-approve \
  -no-color \
  -var "keystone_port=$KEYSTONE_PORT" \
  -var "nova_port=$NOVA_PORT"

echo "=== terraform state check ==="
terraform state list
SERVER_ID=$(terraform output -raw server_id 2>/dev/null)
VOLUME_ID=$(terraform output -raw volume_id 2>/dev/null)
echo "  server_id: $SERVER_ID"
echo "  volume_id: $VOLUME_ID"

echo "=== terraform destroy ==="
terraform destroy \
  -auto-approve \
  -no-color \
  -var "keystone_port=$KEYSTONE_PORT" \
  -var "nova_port=$NOVA_PORT"

echo "=== TERRAFORM TEST PASSED ==="
