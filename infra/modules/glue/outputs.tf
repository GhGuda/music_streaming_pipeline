output "validate_job_name" {
  description = "Glue validation job name."
  value       = aws_glue_job.validate_inputs.name
}

output "compute_job_name" {
  description = "Glue KPI compute job name."
  value       = aws_glue_job.compute_kpis.name
}

output "load_job_name" {
  description = "Glue DynamoDB load job name."
  value       = aws_glue_job.load_dynamodb.name
}
