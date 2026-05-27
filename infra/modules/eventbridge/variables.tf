variable "name_prefix" {
  description = "Prefix used for EventBridge and DLQ resources."
  type        = string
}

variable "environment" {
  description = "Environment name."
  type        = string
}

variable "raw_bucket_name" {
  description = "Raw bucket name used in event pattern."
  type        = string
}

variable "state_machine_arn" {
  description = "Target Step Functions state machine ARN."
  type        = string
}

variable "eventbridge_role_arn" {
  description = "IAM role ARN for EventBridge target invocation."
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key ARN used for DLQ encryption."
  type        = string
}

variable "tags" {
  description = "Common resource tags."
  type        = map(string)
  default     = {}
}
