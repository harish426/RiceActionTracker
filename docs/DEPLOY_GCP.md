# Deploying to Google Cloud

Architecture: **Cloud Scheduler** → **Cloud Run Jobs** (this container) → **Firestore** (state),
**Cloud Storage** (page snapshots), **Secret Manager** (tokens). No servers to manage; cost is
typically a few dollars a month or less.

| Job | Schedule (IST) | Command |
|---|---|---|
| `rice-tracker-tier1` | every 15 min | `tracker run --tier 1` |
| `rice-tracker-tier2` | hourly | `tracker run --tier 2` |
| `rice-tracker-tier3` | every 6 h | `tracker run --tier 3` |
| `rice-tracker-digest` | Mondays 09:00 | `tracker digest` |

## Prerequisites

- A Google Cloud project with **billing enabled**
- `gcloud` CLI installed and logged in: `gcloud auth login`
- Local setup working first (see [LOCAL.md](LOCAL.md)) and `make test` passing
- Sources verified locally with `tracker test-source`

## Steps

```bash
cp deploy/cloud.env.example deploy/cloud.env     # edit PROJECT_ID, BUCKET, emails
deploy/deploy.sh setup      # enables APIs; creates Firestore, bucket, Artifact Registry, service account
deploy/deploy.sh secrets    # prompts for Telegram token/chat id, SMTP password, Anthropic key
deploy/deploy.sh deploy     # builds image with Cloud Build, creates jobs + scheduler triggers
deploy/deploy.sh run tier1  # run once manually and watch the logs
```

First run per source is a baseline (no alerts). If you want existing notices alerted once, run
a one-off: `gcloud run jobs execute rice-tracker-tier1 --args=run,--tier,1,--alert-existing`
(only do this before the first scheduled run baselines them).

## Changing things later

| Change | Do |
|---|---|
| Add/edit websites, change code | edit, then `deploy/deploy.sh deploy` (sources.yaml is baked into the image) |
| Rotate a secret | `deploy/deploy.sh secrets` (new version; jobs use `latest`) |
| Change schedules | edit the `JOBS` table in `deploy/deploy.sh`, redeploy |
| JS-heavy sites | `WITH_BROWSER=1` in `deploy/cloud.env`, redeploy (bigger image, slower build) |

## Operating

- Logs: Cloud Console → Cloud Run → Jobs → executions, or
  `gcloud logging read 'resource.type=cloud_run_job' --limit 50`
- State: Firestore collections `source_state`, `alerts`, `seen_<source-id>`
- Pause everything: `gcloud scheduler jobs pause rice-tracker-tier1 --location asia-south1` (etc.)
- Alert on job failures: Cloud Monitoring → alert on `run.googleapis.com/job/completed_task_attempt_count`
  with `result=failed` (the tracker itself already messages you about sick *websites*).

## Cost (rough)

Cloud Run (a ~10 s job every 15 min), Scheduler (first 3 jobs free, $0.10/job after), Firestore,
Secret Manager and Storage mostly sit in free tiers. Expect **< $1–5/month**, plus LLM usage
(cents). The browser image costs more runtime only on sites that need it.

## Notes & gotchas

- Region `asia-south1` (Mumbai) is the default - lowest latency to Indian sites. Some government
  sites block foreign/cloud IPs; if a source fails only in the cloud, see "Risks" in
  [ARCHITECTURE.md](ARCHITECTURE.md).
- Firestore reads grow with the number of remembered items per source (one read per item per run).
  This is fine for hundreds of items per site; if a source has tens of thousands, prune with a TTL.
- The runtime service account has only Firestore, Secret Accessor, Storage and Run-invoker roles.
- Test locally against real Firestore (optional):
  `gcloud auth application-default login`, then run with `STORAGE_BACKEND=firestore GOOGLE_CLOUD_PROJECT=<id>`.
- CI/CD: `.github/workflows/ci.yml` runs lint + tests on every push. Add a deploy job (Workload
  Identity Federation recommended) once you're happy.
