output "key_arn" {
  description = "ARN of the KMS key used for data encryption."
  value       = aws_kms_key.data.arn
}

output "key_id" {
  description = "ID of the KMS key."
  value       = aws_kms_key.data.key_id
}

output "alias_name" {
  description = "Alias name for the KMS key."
  value       = aws_kms_alias.data.name
}
