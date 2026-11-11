terraform {
  required_version = ">= 1.9, < 2.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 8.11"
    }
  }

  # Remote state placeholder. Create the bucket first, then run
  #   terraform init -backend-config="bucket=<your-state-bucket>"
  # Nothing in this repository runs `terraform apply`.
  backend "gcs" {
    prefix = "dealdesk/state"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
