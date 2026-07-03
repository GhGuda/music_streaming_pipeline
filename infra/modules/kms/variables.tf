variable "name_prefix" {
  description = "Prefix used to name KMS resources."
  type        = string
}

variable "environment" {
  description = "Deployment environment name (for tags)."
  type        = string
}

variable "tags" {
  description = "Common resource tags."
  type        = map(string)
  default     = {}
}
