#!/usr/bin/env bash
# One-command deploy to Google Cloud. Idempotent: safe to re-run after code or sources.yaml changes.
#   cp deploy/cloud.env.example deploy/cloud.env   # edit it
#   deploy/deploy.sh setup     # once: APIs, Firestore, bucket, secrets placeholders, service account
#   deploy/deploy.sh secrets   # set secret values (interactive prompts)
#   deploy/deploy.sh deploy    # build image, create/update Cloud Run Jobs + Scheduler
#   deploy/deploy.sh run tier1 # manually trigger a job once
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
source deploy/cloud.env

SA_NAME=rice-tracker-runner
SA="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${IMAGE_NAME}:latest"
SECRETS=(TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID SMTP_PASSWORD ANTHROPIC_API_KEY)

# job name -> "cron|args"
declare -A JOBS=(
  [rice-tracker-tier1]="*/15 * * * *|run,--tier,1"
  [rice-tracker-tier2]="0 * * * *|run,--tier,2"
  [rice-tracker-tier3]="0 */6 * * *|run,--tier,3"
  [rice-tracker-digest]="0 9 * * 1|digest"
)

gc() { gcloud --project "$PROJECT_ID" "$@"; }

setup() {
  gc services enable run.googleapis.com cloudscheduler.googleapis.com firestore.googleapis.com \
    secretmanager.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com storage.googleapis.com
  gc firestore databases create --location="$REGION" --type=firestore-native 2>/dev/null || echo "Firestore exists"
  gc storage buckets create "gs://${BUCKET}" --location="$REGION" 2>/dev/null || echo "Bucket exists"
  gc artifacts repositories create "$REPO" --repository-format=docker --location="$REGION" 2>/dev/null || echo "Repo exists"
  gc iam service-accounts create "$SA_NAME" --display-name="Rice tracker runner" 2>/dev/null || echo "SA exists"
  for role in roles/datastore.user roles/secretmanager.secretAccessor roles/storage.objectAdmin roles/run.invoker; do
    gc projects add-iam-policy-binding "$PROJECT_ID" --member="serviceAccount:${SA}" --role="$role" --condition=None >/dev/null
  done
  for s in "${SECRETS[@]}"; do
    gc secrets describe "$s" >/dev/null 2>&1 || gc secrets create "$s" --replication-policy=automatic
  done
  echo "Setup done. Next: deploy/deploy.sh secrets"
}

secrets() {
  for s in "${SECRETS[@]}"; do
    read -r -s -p "Value for $s (empty = skip): " v; echo
    [[ -n "$v" ]] && printf '%s' "$v" | gc secrets versions add "$s" --data-file=-
  done
  true
}

# Secrets with no version yet would break the job; give skipped ones an empty value.
ensure_secret_versions() {
  for s in "${SECRETS[@]}"; do
    gc secrets versions list "$s" --limit=1 --format='value(name)' | grep -q . || printf '' | gc secrets versions add "$s" --data-file=-
  done
}

deploy() {
  ensure_secret_versions
  gc builds submit --region "$REGION" --config deploy/cloudbuild.yaml \
    --substitutions "_IMAGE=${IMAGE},_WITH_BROWSER=${WITH_BROWSER}" .
  # '^@^' makes gcloud split env vars on '@' so COMMODITIES=rice,maize keeps its comma
  local env="^@^STORAGE_BACKEND=firestore@SNAPSHOT_BACKEND=gcs@GCS_BUCKET=${BUCKET}@GOOGLE_CLOUD_PROJECT=${PROJECT_ID}"
  env+="@COMMODITIES=${COMMODITIES:-rice,maize}"
  env+="@EMAIL_FROM=${EMAIL_FROM}@EMAIL_TO=${EMAIL_TO}@SMTP_HOST=${SMTP_HOST}@SMTP_PORT=${SMTP_PORT}@SMTP_USER=${SMTP_USER}"
  [[ "$WITH_BROWSER" == "1" ]] && env+="@BROWSER_ENABLED=true"
  local sec=""; for s in "${SECRETS[@]}"; do sec+="${s}=${s}:latest,"; done; sec="${sec%,}"

  for job in "${!JOBS[@]}"; do
    IFS='|' read -r cron args <<<"${JOBS[$job]}"
    gc run jobs deploy "$job" --image "$IMAGE" --region "$REGION" --service-account "$SA" \
      --args "$args" --set-env-vars "$env" --set-secrets "$sec" --max-retries 1 --task-timeout 900s \
      --memory 1Gi
    local uri="https://run.googleapis.com/v2/projects/${PROJECT_ID}/locations/${REGION}/jobs/${job}:run"
    if gc scheduler jobs describe "$job" --location "$REGION" >/dev/null 2>&1; then verb=update; else verb=create; fi
    gc scheduler jobs "$verb" http "$job" --location "$REGION" --schedule "$cron" --time-zone "$TIMEZONE" \
      --uri "$uri" --http-method POST --oauth-service-account-email "$SA"
  done
  echo "Deployed. Test now: deploy/deploy.sh run tier1"
}

run_job() { gc run jobs execute "rice-tracker-${1}" --region "$REGION" --wait; }

case "${1:-}" in
  setup) setup ;; secrets) secrets ;; deploy) deploy ;; run) run_job "${2:?tier1|tier2|tier3|digest}" ;;
  *) sed -n '2,8p' "$0"; exit 1 ;;
esac
