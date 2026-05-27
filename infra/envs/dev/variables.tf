variable "aws_region" {
  description = "AWS region for dev deployment."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project identifier used in naming."
  type        = string
  default     = "music-streaming"
}

variable "environment" {
  description = "Environment name."
  type        = string
  default     = "dev"
}

variable "owner" {
  description = "Owner tag value."
  type        = string
  default     = "data-platform"
}

variable "cost_center" {
  description = "Cost-center tag value."
  type        = string
  default     = "engineering"
}
