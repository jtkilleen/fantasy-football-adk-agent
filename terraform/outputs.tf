output "service_account_email" {
  description = "Email of the least-privilege service account provisioned for the Fantasy Football Personal Agent."
  value       = google_service_account.fantasy_agent_sa.email
}

output "secret_manager_secret_id" {
  description = "Google Cloud Secret Manager secret ID configured for the agent runtime."
  value       = google_secret_manager_secret.fantasy_agent_config.secret_id
}

output "agent_engine_staging_bucket_url" {
  description = "GCS staging bucket URI used by `uv run adk deploy agent_engine`."
  value       = google_storage_bucket.agent_engine_staging.url
}

output "artifact_registry_repository_id" {
  description = "Artifact Registry Docker repository ID for Cloud Run container deployments."
  value       = google_artifact_registry_repository.agent_repo.repository_id
}

output "adk_deploy_agent_engine_command" {
  description = "Ready-to-run ADK CLI command to deploy the Fantasy Football Personal Agent to Vertex AI Agent Engine."
  value       = "uv run adk deploy agent_engine --project=${var.project_id} --region=${var.region} --display_name=\"Fantasy Football Personal Agent\" --otel_to_cloud fantasy_agent"
}

output "adk_deploy_cloud_run_command" {
  description = "Ready-to-run ADK CLI command to deploy the Fantasy Football Personal Agent to Google Cloud Run."
  value       = "uv run adk deploy cloud_run --project=${var.project_id} --region=${var.region} --service_name=fantasy-football-agent --with_ui fantasy_agent"
}
