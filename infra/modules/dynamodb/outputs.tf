output "table_name" {
  description = "DynamoDB KPI table name."
  value       = aws_dynamodb_table.kpis.name
}

output "table_arn" {
  description = "DynamoDB KPI table ARN."
  value       = aws_dynamodb_table.kpis.arn
}
