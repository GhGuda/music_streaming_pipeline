variable "name_prefix" {
  description = "Prefix used for dashboard resources."
  type        = string
}

variable "environment" {
  description = "Environment name."
  type        = string
}

variable "lambda_role_arn" {
  description = "IAM role ARN for the KPI API Lambda."
  type        = string
}

variable "dynamodb_table_name" {
  description = "KPI DynamoDB table name."
  type        = string
}

variable "tags" {
  description = "Common resource tags."
  type        = map(string)
  default     = {}
}
