variable "project_id" {
  description = "Google Cloud Project ID where Vertex AI Agent Engine, Secret Manager, and observability resources are provisioned."
  type        = string
}

variable "region" {
  description = "Default Google Cloud region for Vertex AI Agent Engine and regional resources."
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Deployment environment label (e.g., dev, staging, prod)."
  type        = string
  default     = "prod"
}

variable "agent_service_account_id" {
  description = "Account ID for the least-privilege Fantasy Football Agent service account."
  type        = string
  default     = "fantasy-football-agent-sa"
}

variable "secret_id" {
  description = "Google Cloud Secret Manager secret ID used by fantasy_agent/config.py."
  type        = string
  default     = "fantasy-agent-api-config"
}
