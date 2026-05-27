variable "name_prefix" {
  description = "Prefix used in the DynamoDB table name."
  type        = string
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key ARN used for table encryption."
  type        = string
}

variable "enable_gsi1" {
  description = "Whether to create gsi1 for genre/date queries."
  type        = bool
  default     = true
}

variable "tags" {
  description = "Common resource tags."
  type        = map(string)
  default     = {}
}
