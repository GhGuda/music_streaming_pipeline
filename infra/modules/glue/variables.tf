variable "name_prefix" {
  description = "Prefix used for Glue job names."
  type        = string
}

variable "environment" {
  description = "Environment name."
  type        = string
}

variable "glue_role_arn" {
  description = "IAM role ARN for Glue jobs."
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

variable "scripts_bucket_name" {
  description = "Scripts S3 bucket name."
  type        = string
}

variable "dynamodb_table_name" {
  description = "DynamoDB table name."
  type        = string
}

variable "tags" {
  description = "Common resource tags."
  type        = map(string)
  default     = {}
}
