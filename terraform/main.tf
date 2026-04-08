resource "google_container_cluster" "primary" {
  name     = var.cluster_name
  location = var.zone

  # GKE requires at least one node on creation. We remove the default node pool
  # immediately and replace it with our own below — this gives us full control
  # over node pool configuration without the cluster enforcing defaults.
  remove_default_node_pool = true
  initial_node_count       = 1

  # Disabled so terraform destroy can cleanly delete the cluster.
  # In production you'd leave this true to prevent accidental deletion.
  deletion_protection = false

  # Workload Identity lets pods authenticate to Google APIs (e.g. Cloud Storage,
  # Pub/Sub) without hardcoding service account key files into containers.
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }
}

resource "google_container_node_pool" "primary_nodes" {
  name       = "${var.cluster_name}-node-pool"
  location   = var.zone
  cluster    = google_container_cluster.primary.name
  node_count = var.node_count

  node_config {
    machine_type = var.machine_type

    # 30GB is the GKE minimum and sufficient for running containers.
    # Default is 100GB — at 3 nodes that's 300GB SSD which exceeds
    # the free tier quota. 3 × 30GB = 90GB, well within limits.
    disk_size_gb = 30
    disk_type    = "pd-standard"

    # cloud-platform scope grants access to all Google Cloud APIs.
    # Required for the nodes to pull images from Artifact Registry.
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform"
    ]

    labels = {
      project = "traffic-priority"
    }
  }
}
