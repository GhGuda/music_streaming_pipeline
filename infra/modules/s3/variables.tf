variable "name_prefix" {
  description = "Prefix used in bucket names."
  type        = string
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key ARN used for S3 server-side encryption."
  type        = string
}

variable "tags" {
  description = "Common resource tags."
  type        = map(string)
  default     = {}
}

variable "force_destroy_buckets" {
  description = "If true, `terraform destroy` empties versioned buckets before deleting them. Safe for dev/learning; set to false if you ever store data you can't lose."
  type        = bool
  default     = true
}
