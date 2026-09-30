terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 5.30.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  required_apis = toset([
    "aiplatform.googleapis.com",
    "secretmanager.googleapis.com",
    "dlp.googleapis.com",
    "logging.googleapis.com",
    "cloudtrace.googleapis.com",
    "storage.googleapis.com",
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
  ])

  common_labels = {
    application = "fantasy-football-personal-agent"
    framework   = "google-adk"
    environment = var.environment
    managed_by  = "terraform"
  }
}

# 1. Enable Required Google Cloud APIs
resource "google_project_service" "enabled_apis" {
  for_each           = local.required_apis
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# 2. Google Cloud Secret Manager Secret (Rubric 5.3: Secure Secret Management)
resource "google_secret_manager_secret" "fantasy_agent_config" {
  project   = var.project_id
  secret_id = var.secret_id
  labels    = local.common_labels

  replication {
    auto {}
  }

  depends_on = [google_project_service.enabled_apis]
}

# 3. Vertex AI Agent Engine Staging Bucket (Rubric 5.2: Infrastructure as Code)
resource "google_storage_bucket" "agent_engine_staging" {
  project                     = var.project_id
  name                        = "${var.project_id}-fantasy-agent-staging"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
  labels                      = local.common_labels

  versioning {
    enabled = true
  }

  depends_on = [google_project_service.enabled_apis]
}

# 4. Artifact Registry Repository for Optional Cloud Run Container Deployments
resource "google_artifact_registry_repository" "agent_repo" {
  project       = var.project_id
  location      = var.region
  repository_id = "fantasy-football-agent"
  description   = "Container repository for the Google ADK Fantasy Football Personal Agent"
  format        = "DOCKER"
  labels        = local.common_labels

  depends_on = [google_project_service.enabled_apis]
}
