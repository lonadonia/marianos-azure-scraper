#!/usr/bin/env bash
# Build the image in Azure Container Registry and deploy the jobs (azure/main.bicep).
#
#   azure/deploy.sh <resource-group> <registry> [parameters-file]
#
# Prerequisites (docs/AZURE.md): `az login`; the registry, Key Vault (with the two secrets), storage account
# and PostgreSQL server exist; the parameters file is filled in (copy azure/main.parameters.example.json).
# This script never reads or prints a secret value. It starts no collection: the scheduled jobs act only
# when the configuration's schedule is enabled and the store-local start time comes.
set -euo pipefail
RG="${1:?resource group}"
ACR="${2:?registry name}"
PARAMS="${3:-azure/main.parameters.json}"
VERSION="$(python3 -c 'import tomllib;print(tomllib.load(open("pyproject.toml","rb"))["project"]["version"])')"
COMMIT="$(git rev-parse HEAD 2>/dev/null || echo unknown)"
IMAGE="${ACR}.azurecr.io/marianos-collector:${VERSION}"

echo "building ${IMAGE} (commit ${COMMIT})"
az acr build --registry "$ACR" --image "marianos-collector:${VERSION}" \
  --build-arg SOURCE_COMMIT="$COMMIT" --build-arg BUILT_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)" .

echo "deploying the jobs"
az deployment group create --resource-group "$RG" --template-file azure/main.bicep \
  --parameters "@${PARAMS}" --parameters image="$IMAGE" --query properties.outputs -o json

OPS="$(az deployment group show -g "$RG" -n main --query properties.outputs.opsJob.value -o tsv)"
ops() {  # run one collector command in the operations job
  az containerapp job update --name "$OPS" --resource-group "$RG" --set-env-vars "MARIANOS_COLLECTOR_COMMAND=$1" -o none
  az containerapp job start --name "$OPS" --resource-group "$RG" -o none
}
echo "creating or upgrading the database schema (ops job ${OPS})"
ops "db-upgrade"
echo "next, once the schema job has finished: ops job with 'validate-config --check-db --require-credentials'"
echo "(see docs/AZURE.md: Operations). No collection was started."
