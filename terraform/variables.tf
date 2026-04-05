variable "project_id" {
  description = "GCP project ID"
  type        = string
  default     = "traffic-priority-ahan"
}

variable "region" {
  description = "GCP region to deploy into"
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "GCP zone for the node pool"
  type        = string
  default     = "us-central1-a"
}

variable "cluster_name" {
  description = "Name of the GKE cluster"
  type        = string
  default     = "traffic-priority-cluster"
}

variable "node_count" {
  description = "Number of nodes in the cluster"
  type        = number
  default     = 2
}

variable "machine_type" {
  description = "GCE machine type for cluster nodes — e2-standard-2 = 2 vCPU, 8GB RAM"
  type        = string
  default     = "e2-standard-2"
}
