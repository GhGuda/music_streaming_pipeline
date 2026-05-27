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

output "dynamodb_table_name" {
  description = "DynamoDB KPI table name."
  value       = module.dynamodb.table_name
}

output "glue_role_arn" {
  description = "Glue role ARN."
  value       = module.iam.glue_role_arn
}

output "lambda_role_arn" {
  description = "Lambda role ARN."
  value       = module.iam.lambda_role_arn
}

output "step_functions_role_arn" {
  description = "Step Functions role ARN."
  value       = module.iam.step_functions_role_arn
}

output "eventbridge_role_arn" {
  description = "EventBridge role ARN."
  value       = module.iam.eventbridge_role_arn
}

output "archive_success_lambda_arn" {
  description = "Archive success Lambda ARN."
  value       = module.lambda.archive_success_arn
}

output "archive_failure_lambda_arn" {
  description = "Archive failure Lambda ARN."
  value       = module.lambda.archive_failure_arn
}

output "state_machine_arn" {
  description = "Step Functions state machine ARN."
  value       = module.step_functions.state_machine_arn
}

output "state_machine_name" {
  description = "Step Functions state machine name."
  value       = module.step_functions.state_machine_name
}
