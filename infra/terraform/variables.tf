variable "project_id" {
  description = "GCP project to deploy into. No real project id is committed; pass it at plan time."
  type        = string
}

variable "region" {
  description = "Region for Cloud Run, Cloud SQL and Artifact Registry (London by default)."
  type        = string
  default     = "europe-west2"
}

variable "environment" {
  description = "Short environment name used in resource names (for example staging or prod)."
  type        = string
  default     = "staging"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,15}$", var.environment))
    error_message = "Use 2 to 16 lowercase letters, digits or hyphens."
  }
}

variable "api_image" {
  description = "Full Artifact Registry image reference for the API (pinned by digest in real deployments)."
  type        = string
}

variable "web_image" {
  description = "Full Artifact Registry image reference for the web front end."
  type        = string
}

variable "db_tier" {
  description = "Cloud SQL machine tier."
  type        = string
  default     = "db-custom-1-3840"
}

variable "db_deletion_protection" {
  description = "Protect the database from accidental deletion. Keep true outside throwaway environments."
  type        = bool
  default     = true
}

variable "llm_provider" {
  description = "Model provider for the API: fake (offline), vertex, anthropic or openai."
  type        = string
  default     = "vertex"

  validation {
    condition     = contains(["fake", "vertex", "anthropic", "openai"], var.llm_provider)
    error_message = "llm_provider must be one of fake, vertex, anthropic, openai."
  }
}

variable "llm_model" {
  description = "Model name for the configured provider (read from configuration, never hard-coded)."
  type        = string
  default     = ""
}

variable "auth_mode" {
  description = "local (passwords and our own tokens) or oidc (an external identity provider)."
  type        = string
  default     = "oidc"

  validation {
    condition     = contains(["local", "oidc"], var.auth_mode)
    error_message = "auth_mode must be local or oidc."
  }
}

variable "public_origin" {
  description = "The public HTTPS origin of the web front end (used for the CSRF Origin check)."
  type        = string
}

variable "oidc" {
  description = "Identity-provider settings used when auth_mode is oidc."
  type = object({
    issuer        = string
    audience      = string
    jwks_url      = string
    client_id     = string
    authorize_url = string
    token_url     = string
  })
  default = {
    issuer        = ""
    audience      = ""
    jwks_url      = ""
    client_id     = ""
    authorize_url = ""
    token_url     = ""
  }
}

variable "vpc_cidr" {
  description = "CIDR for the subnet used by Cloud Run Direct VPC egress (web to internal API)."
  type        = string
  default     = "10.10.0.0/24"
}

variable "api_max_instances" {
  description = "Upper bound on API instances. The in-memory rate limiter is per instance (see docs/SECURITY.md)."
  type        = number
  default     = 3
}
