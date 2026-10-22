#!/usr/bin/env bash
# Idempotent infra + deploy for the DarwinLoop dashboard on Cloud Run (brain003-mvp). Creates nothing destructive.
set -euo pipefail
P=brain003-mvp; R=southamerica-east1; SVC=darwinloop-dash; DS=darwinloop_telemetry
SA=$SVC@$P.iam.gserviceaccount.com
cd "$(dirname "$0")"

# One-time infra; CI (GitHub sets CI=true) only applies views and deploys, so its deployer SA stays least-privilege.
if [ -z "${CI:-}" ]; then
gcloud iam service-accounts describe $SA --project $P >/dev/null 2>&1 ||
  gcloud iam service-accounts create $SVC --project $P --display-name "DarwinLoop dashboard"

for s in dl-ingest-token dl-dash-pass; do  # random values go straight into Secret Manager, never printed
  gcloud secrets describe $s --project $P >/dev/null 2>&1 ||
    openssl rand -hex 24 | tr -d '\n' | gcloud secrets create $s --project $P --replication-policy automatic --data-file=-
  gcloud secrets add-iam-policy-binding $s --project $P --member serviceAccount:$SA \
    --role roles/secretmanager.secretAccessor >/dev/null
done

gcloud projects add-iam-policy-binding $P --member serviceAccount:$SA --role roles/bigquery.jobUser --condition=None >/dev/null
bq query --use_legacy_sql=false "GRANT \`roles/bigquery.dataEditor\` ON SCHEMA \`$P.$DS\` TO \"serviceAccount:$SA\"" >/dev/null
fi

bq query --use_legacy_sql=false < views.sql >/dev/null

gcloud run deploy $SVC --project $P --region $R --source . --service-account $SA \
  --allow-unauthenticated `# OTLP clients cannot send Google ID tokens; auth is Bearer (ingest) + Basic (UI) in-app` \
  --set-env-vars BQ_PROJECT=$P,BQ_DATASET=$DS,DASH_USER=darwin \
  --set-secrets INGEST_TOKEN=dl-ingest-token:latest,DASH_PASS=dl-dash-pass:latest \
  --memory 512Mi --max-instances 3 --quiet

gcloud run services describe $SVC --project $P --region $R --format 'value(status.url)'
