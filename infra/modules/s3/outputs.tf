output "raw_bucket_name" {
  description = "Raw data bucket name."
  value       = aws_s3_bucket.raw.id
}

output "processed_bucket_name" {
  description = "Processed data bucket name."
  value       = aws_s3_bucket.processed.id
}

output "archive_bucket_name" {
  description = "Archive bucket name."
  value       = aws_s3_bucket.archive.id
}

output "scripts_bucket_name" {
  description = "Bucket for Glue/Lambda scripts."
  value       = aws_s3_bucket.scripts.id
}
