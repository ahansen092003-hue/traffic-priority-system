# ── Secret Manager API ────────────────────────────────────────────────────────
resource "google_project_service" "secretmanager" {
  service            = "secretmanager.googleapis.com"
  disable_on_destroy = false
}

# ── Secrets (values set manually via gcloud after terraform apply) ─────────────
resource "google_secret_manager_secret" "anthropic_api_key" {
  secret_id = "anthropic-api-key"
  replication {
    auto {}
  }
  depends_on = [google_project_service.secretmanager]
}

resource "google_secret_manager_secret" "postgres_password" {
  secret_id = "postgres-password"
  replication {
    auto {}
  }
  depends_on = [google_project_service.secretmanager]
}

# ── Google Service Account for secret access ──────────────────────────────────
resource "google_service_account" "secrets_accessor" {
  account_id   = "traffic-secrets-accessor"
  display_name = "Traffic Priority — Secret Accessor"
}

resource "google_project_iam_member" "secrets_accessor" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.secrets_accessor.email}"
}

# ── Workload Identity binding: KSA → GSA ──────────────────────────────────────
# Allows pods using the 'secret-accessor' Kubernetes ServiceAccount to
# impersonate the GSA above — no key files, no hardcoded credentials.
resource "google_service_account_iam_member" "workload_identity_binding" {
  service_account_id = google_service_account.secrets_accessor.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[default/secret-accessor]"
}
