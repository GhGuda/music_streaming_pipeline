variable "name_prefix" {
  description = "Prefix used to name IAM resources."
  type        = string
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key ARN used by pipeline services."
  type        = string
}

variable "raw_bucket_name" {
  description = "Raw S3 bucket name."
  type        = string
}

variable "processed_bucket_name" {
  description = "Processed S3 bucket name."
  type        = string
}

variable "archive_bucket_name" {
  description = "Archive S3 bucket name."
  type        = string
}

variable "scripts_bucket_name" {
  description = "Scripts S3 bucket name."
  type        = string
}

variable "dynamodb_table_arn" {
  description = "DynamoDB table ARN."
  type        = string
}

variable "tags" {
  description = "Common resource tags."
  type        = map(string)
  default     = {}
}
