output "cluster_name" {
  value       = google_container_cluster.primary.name
  description = "GKE cluster name"
}

output "cluster_endpoint" {
  value       = google_container_cluster.primary.endpoint
  description = "GKE cluster API endpoint — used by kubectl and Prefect"
  sensitive   = true
}

output "region" {
  value       = var.region
  description = "Region the cluster was deployed to"
}

output "get_credentials_command" {
  value       = "gcloud container clusters get-credentials ${var.cluster_name} --zone ${var.zone} --project ${var.project_id}"
  description = "Run this after terraform apply to configure kubectl to talk to this cluster"
}
