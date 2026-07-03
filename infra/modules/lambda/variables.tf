variable "name_prefix" {
  description = "Prefix used for Lambda function names."
  type        = string
}

variable "environment" {
  description = "Environment name."
  type        = string
}

variable "lambda_role_arn" {
  description = "IAM role ARN for Lambda execution."
  type        = string
}

variable "archive_bucket_name" {
  description = "Destination archive bucket name."
  type        = string
}

variable "tags" {
  description = "Common resource tags."
  type        = map(string)
  default     = {}
}
