variable "name_prefix" {
  description = "Prefix used for Step Functions resources."
  type        = string
}

variable "environment" {
  description = "Environment name."
  type        = string
}

variable "step_functions_role_arn" {
  description = "IAM role ARN for Step Functions."
  type        = string
}

variable "asl_template_path" {
  description = "Path to ASL JSON template."
  type        = string
}

variable "validate_job_name" {
  type = string
}

variable "compute_job_name" {
  type = string
}

variable "load_job_name" {
  type = string
}

variable "scripts_bucket" {
  type = string
}

variable "raw_bucket" {
  type = string
}

variable "processed_bucket" {
  type = string
}

variable "dynamodb_table" {
  type = string
}

variable "archive_success_arn" {
  type = string
}

variable "archive_failure_arn" {
  type = string
}

variable "tags" {
  description = "Common resource tags."
  type        = map(string)
  default     = {}
}
