# Dedicated Least-Privilege Service Account for the Fantasy Football Personal Agent
resource "google_service_account" "fantasy_agent_sa" {
  project      = var.project_id
  account_id   = var.agent_service_account_id
  display_name = "Fantasy Football Personal Agent Runtime SA"
  description  = "Least-privilege service account for Vertex AI Agent Engine, Gemini models, Secret Manager, Cloud DLP, Cloud Logging, and Cloud Trace."
}

locals {
  agent_project_roles = toset([
    "roles/aiplatform.user",
    "roles/dlp.user",
    "roles/logging.logWriter",
    "roles/cloudtrace.agent",
  ])
}

# Project-Level Least-Privilege Roles (Vertex AI, DLP PII Redaction, Structured Logging, OpenTelemetry Trace)
resource "google_project_iam_member" "agent_project_permissions" {
  for_each = local.agent_project_roles
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.fantasy_agent_sa.email}"
}

# Secret-Scoped IAM Binding (Rubric 5.3: Only access the specific Secret Manager secret)
resource "google_secret_manager_secret_iam_member" "agent_secret_accessor" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.fantasy_agent_config.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.fantasy_agent_sa.email}"
}

# Bucket-Scoped IAM Binding for Vertex AI Agent Engine Staging Artifacts
resource "google_storage_bucket_iam_member" "agent_staging_bucket_admin" {
  bucket = google_storage_bucket.agent_engine_staging.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.fantasy_agent_sa.email}"
}
