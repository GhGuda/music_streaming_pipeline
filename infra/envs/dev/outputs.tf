output "kms_key_arn" {
  description = "KMS key ARN used by foundational resources."
  value       = module.kms.key_arn
}

output "raw_bucket_name" {
  description = "Raw data bucket."
  value       = module.s3.raw_bucket_name
}

output "processed_bucket_name" {
  description = "Processed data bucket."
  value       = module.s3.processed_bucket_name
}

output "archive_bucket_name" {
  description = "Archive bucket."
  value       = module.s3.archive_bucket_name
}

output "scripts_bucket_name" {
  description = "Scripts/artifacts bucket."
  value       = module.s3.scripts_bucket_name
}
