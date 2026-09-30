"""Unit tests for Milestone 7: Terraform Infrastructure as Code, Documentation & Public Repo Hygiene."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TERRAFORM_DIR = REPO_ROOT / "terraform"
README_PATH = REPO_ROOT / "README.md"


def test_terraform_files_exist_and_define_required_gcp_resources() -> None:
    """Verify Rubric 5.2: Complete Terraform IaC configuration for GCP & Vertex AI Agent Engine."""
    expected_files = ["main.tf", "variables.tf", "iam.tf", "outputs.tf"]
    combined_hcl = ""

    for filename in expected_files:
        tf_path = TERRAFORM_DIR / filename
        assert tf_path.is_file(), f"Missing Terraform file: {filename}"
        content = tf_path.read_text(encoding="utf-8")
        # Verify balanced curly braces in every .tf file
        assert content.count("{") == content.count("}"), f"Unbalanced braces in {filename}"
        assert content.count("{") > 0
        combined_hcl += "\n" + content

    # Required GCP resources & least-privilege IAM bindings
    assert 'resource "google_project_service" "enabled_apis"' in combined_hcl
    assert 'resource "google_secret_manager_secret" "fantasy_agent_config"' in combined_hcl
    assert 'resource "google_storage_bucket" "agent_engine_staging"' in combined_hcl
    assert 'resource "google_artifact_registry_repository" "agent_repo"' in combined_hcl
    assert 'resource "google_service_account" "fantasy_agent_sa"' in combined_hcl
    assert 'resource "google_secret_manager_secret_iam_member" "agent_secret_accessor"' in combined_hcl
    assert 'resource "google_storage_bucket_iam_member" "agent_staging_bucket_admin"' in combined_hcl
    assert "aiplatform.googleapis.com" in combined_hcl
    assert "secretmanager.googleapis.com" in combined_hcl
    assert "dlp.googleapis.com" in combined_hcl


def test_readme_documents_adk_cli_terraform_and_19_rubric_criteria() -> None:
    """Verify Rubric 5.2: README.md documents ADK CLI, Terraform, and all 19 rubric criteria."""
    assert README_PATH.is_file()
    readme = README_PATH.read_text(encoding="utf-8")

    # Required CLI and IaC commands
    assert "uv run adk run fantasy_agent" in readme
    assert "uv run adk web" in readme
    assert "uv run adk eval fantasy_agent" in readme
    assert "uv run adk deploy agent_engine" in readme
    assert "terraform -chdir=terraform init" in readme
    assert "terraform -chdir=terraform apply" in readme

    # Verify all 19 AgentOps Code Review Matrix criteria IDs are mapped
    expected_criteria = [
        "1.1", "1.2", "1.3", "1.4",
        "2.1", "2.2", "2.3", "2.4",
        "3.1", "3.2", "3.3", "3.4",
        "4.1", "4.2", "4.3", "4.4",
        "5.1", "5.2", "5.3",
    ]
    for criterion_id in expected_criteria:
        assert f"**{criterion_id}**" in readme, f"Missing rubric criterion {criterion_id} in README.md"


def test_public_repo_hygiene_no_hardcoded_project_id_or_secrets() -> None:
    """Verify no tracked files hardcode private keys, API keys, or non-parameterized Terraform projects."""
    tracked_dirs = [
        REPO_ROOT / "fantasy_agent",
        REPO_ROOT / "tests",
        REPO_ROOT / "terraform",
        REPO_ROOT / "docs",
    ]
    this_file = Path(__file__).resolve()
    files_to_scan = [README_PATH, REPO_ROOT / "pyproject.toml", REPO_ROOT / "GEMINI.md"]
    for directory in tracked_dirs:
        for path in directory.rglob("*"):
            if (
                path.is_file()
                and path.resolve() != this_file
                and ".adk" not in path.parts
                and "__pycache__" not in path.parts
            ):
                files_to_scan.append(path)

    for file_path in files_to_scan:
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        assert "-----BEGIN PRIVATE KEY-----" not in text, f"Private key found in {file_path}"
        assert "-----BEGIN RSA PRIVATE KEY-----" not in text, f"RSA key found in {file_path}"
        assert "AIzaSy" not in text, f"Hardcoded Google API key found in {file_path}"

    # Verify Terraform main.tf parameterizes project via var.project_id
    main_tf = (TERRAFORM_DIR / "main.tf").read_text(encoding="utf-8")
    assert "project = var.project_id" in main_tf
