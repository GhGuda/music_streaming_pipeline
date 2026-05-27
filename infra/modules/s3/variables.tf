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
