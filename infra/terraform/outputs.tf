output "web_url" {
  description = "Public URL of the web front end."
  value       = google_cloud_run_v2_service.web.uri
}

output "api_url" {
  description = "Internal URL of the API (reachable only from inside the VPC / by the web service)."
  value       = google_cloud_run_v2_service.api.uri
}

output "artifact_registry" {
  description = "Docker repository for the API and web images."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
}

output "sql_connection_name" {
  description = "Cloud SQL instance connection name."
  value       = google_sql_database_instance.db.connection_name
}

output "secret_ids" {
  description = "Secret Manager secrets to populate out of band (never through Terraform)."
  value       = { for key, secret in google_secret_manager_secret.secrets : key => secret.secret_id }
}
