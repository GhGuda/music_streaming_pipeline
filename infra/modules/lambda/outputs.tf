output "archive_success_arn" {
  description = "Archive-success Lambda ARN."
  value       = aws_lambda_function.archive_success.arn
}

output "archive_failure_arn" {
  description = "Archive-failure Lambda ARN."
  value       = aws_lambda_function.archive_failure.arn
}
