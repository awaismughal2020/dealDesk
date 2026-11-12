locals {
  name = "dealdesk-${var.environment}"
  apis = [
    "artifactregistry.googleapis.com",
    "run.googleapis.com",
    "sqladmin.googleapis.com",
    "secretmanager.googleapis.com",
    "compute.googleapis.com",
    "aiplatform.googleapis.com",
    "servicenetworking.googleapis.com",
  ]
  # Secrets are created empty here; values are added out of band (never in Terraform state).
  secrets = {
    database_url    = "${local.name}-database-url"
    jwt_signing_key = "${local.name}-jwt-signing-key"
    llm_api_key     = "${local.name}-llm-api-key"
  }
}

resource "google_project_service" "apis" {
  for_each           = toset(local.apis)
  service            = each.value
  disable_on_destroy = false
}

# ---------------------------------------------------------------- images

resource "google_artifact_registry_repository" "images" {
  repository_id = local.name
  location      = var.region
  format        = "DOCKER"
  description   = "Deal Desk container images"

  docker_config {
    immutable_tags = true
  }

  depends_on = [google_project_service.apis]
}

# ---------------------------------------------------------------- identities (least privilege)

resource "google_service_account" "api" {
  account_id   = "${local.name}-api"
  display_name = "Deal Desk API (runtime)"
}

resource "google_service_account" "web" {
  account_id   = "${local.name}-web"
  display_name = "Deal Desk web front end (runtime)"
}

resource "google_project_iam_member" "api_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "api_vertex_user" {
  count   = var.llm_provider == "vertex" ? 1 : 0
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.api.email}"
}

# ---------------------------------------------------------------- secrets

resource "google_secret_manager_secret" "secrets" {
  for_each  = local.secrets
  secret_id = each.value

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_iam_member" "api_access" {
  for_each  = google_secret_manager_secret.secrets
  secret_id = each.value.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

# ---------------------------------------------------------------- network (web -> internal API)

resource "google_compute_network" "vpc" {
  name                    = local.name
  auto_create_subnetworks = false
  depends_on              = [google_project_service.apis]
}

resource "google_compute_subnetwork" "run" {
  name                     = "${local.name}-run"
  network                  = google_compute_network.vpc.id
  region                   = var.region
  ip_cidr_range            = var.vpc_cidr
  private_ip_google_access = true
}

# Private service access so Cloud SQL gets a private IP inside the VPC (no public IP).
resource "google_compute_global_address" "sql_private_range" {
  name          = "${local.name}-sql-range"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 20
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "sql" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.sql_private_range.name]
}

# ---------------------------------------------------------------- database (PostgreSQL 16 + pgvector)

resource "google_sql_database_instance" "db" {
  name                = local.name
  database_version    = "POSTGRES_16"
  region              = var.region
  deletion_protection = var.db_deletion_protection

  settings {
    tier              = var.db_tier
    availability_type = "REGIONAL"
    disk_autoresize   = true

    backup_configuration {
      enabled                        = true
      point_in_time_recovery_enabled = true
    }

    ip_configuration {
      ipv4_enabled    = false
      ssl_mode        = "ENCRYPTED_ONLY"
      private_network = google_compute_network.vpc.id
    }

    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "on"
    }
  }

  depends_on = [google_project_service.apis, google_service_networking_connection.sql]
}

resource "google_sql_database" "app" {
  name     = "dealdesk"
  instance = google_sql_database_instance.db.name
}

# ---------------------------------------------------------------- Cloud Run: API (internal only)

resource "google_cloud_run_v2_service" "api" {
  name                = "${local.name}-api"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_INTERNAL_ONLY"
  deletion_protection = false

  template {
    service_account = google_service_account.api.email

    scaling {
      min_instance_count = 0
      max_instance_count = var.api_max_instances
    }

    vpc_access {
      egress = "PRIVATE_RANGES_ONLY"
      network_interfaces {
        network    = google_compute_network.vpc.id
        subnetwork = google_compute_subnetwork.run.id
      }
    }

    containers {
      image = var.api_image

      ports {
        container_port = 8000
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      env {
        name  = "APP_ENV"
        value = var.environment == "prod" ? "production" : "staging"
      }
      env {
        name  = "COOKIE_SECURE"
        value = "true"
      }
      env {
        name  = "ALLOWED_ORIGINS"
        value = var.public_origin
      }
      env {
        name  = "AUTH_MODE"
        value = var.auth_mode
      }
      env {
        name  = "OIDC_ISSUER"
        value = var.oidc.issuer
      }
      env {
        name  = "OIDC_AUDIENCE"
        value = var.oidc.audience
      }
      env {
        name  = "OIDC_JWKS_URL"
        value = var.oidc.jwks_url
      }
      env {
        name  = "LLM_PROVIDER"
        value = var.llm_provider
      }
      env {
        name  = "LLM_MODEL"
        value = var.llm_model
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.region
      }
      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.secrets["database_url"].secret_id
            version = "latest"
          }
        }
      }

      volume_mounts {
        name       = "jwt-keys"
        mount_path = "/run/dealdesk-keys"
      }

      startup_probe {
        http_get {
          path = "/readyz"
        }
      }
      liveness_probe {
        http_get {
          path = "/healthz"
        }
      }
    }

    volumes {
      name = "jwt-keys"
      secret {
        secret = google_secret_manager_secret.secrets["jwt_signing_key"].secret_id
        items {
          version = "latest"
          path    = "current.pem"
        }
      }
    }
  }

  depends_on = [google_project_service.apis]
}

# Only the web service account may call the API.
resource "google_cloud_run_v2_service_iam_member" "web_invokes_api" {
  name     = google_cloud_run_v2_service.api.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.web.email}"
}

# ---------------------------------------------------------------- Cloud Run: web (public)

resource "google_cloud_run_v2_service" "web" {
  name                = "${local.name}-web"
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = false

  template {
    service_account = google_service_account.web.email

    vpc_access {
      egress = "PRIVATE_RANGES_ONLY"
      network_interfaces {
        network    = google_compute_network.vpc.id
        subnetwork = google_compute_subnetwork.run.id
      }
    }

    containers {
      image = var.web_image

      ports {
        container_port = 3000
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name  = "API_INTERNAL_URL"
        value = google_cloud_run_v2_service.api.uri
      }
      env {
        name  = "APP_ENV"
        value = var.environment == "prod" ? "production" : "staging"
      }
      env {
        name  = "AUTH_MODE"
        value = var.auth_mode
      }
      env {
        name  = "OIDC_CLIENT_ID"
        value = var.oidc.client_id
      }
      env {
        name  = "OIDC_AUTHORIZE_URL"
        value = var.oidc.authorize_url
      }
      env {
        name  = "OIDC_TOKEN_URL"
        value = var.oidc.token_url
      }

      liveness_probe {
        http_get {
          path = "/healthz"
        }
      }
    }
  }

  depends_on = [google_project_service.apis]
}

# The web front end is a public site; it authenticates users itself (cookies + API checks).
resource "google_cloud_run_v2_service_iam_member" "web_public" {
  name     = google_cloud_run_v2_service.web.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
}
