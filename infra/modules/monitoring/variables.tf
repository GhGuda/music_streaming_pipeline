variable "name_prefix" {
  description = "Prefix used for monitoring resources."
  type        = string
}

variable "environment" {
  description = "Environment name."
  type        = string
}

variable "alert_email" {
  description = "Email address subscribed to SNS alerts."
  type        = string
}

variable "state_machine_arn" {
  description = "Step Functions state machine ARN."
  type        = string
}

variable "state_machine_name" {
  description = "Step Functions state machine name."
  type        = string
}

variable "archive_success_function_name" {
  description = "Archive success Lambda function name."
  type        = string
}

variable "archive_failure_function_name" {
  description = "Archive failure Lambda function name."
  type        = string
}

variable "eventbridge_dlq_name" {
  description = "EventBridge DLQ queue name."
  type        = string
}

variable "tags" {
  description = "Common resource tags."
  type        = map(string)
  default     = {}
}
