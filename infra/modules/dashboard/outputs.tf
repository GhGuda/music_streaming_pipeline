output "api_endpoint" {
  description = "HTTP API endpoint for KPI reads."
  value       = aws_apigatewayv2_api.kpi.api_endpoint
}

output "dashboard_bucket_name" {
  description = "S3 bucket hosting the dashboard."
  value       = aws_s3_bucket.dashboard.id
}

output "dashboard_url" {
  description = "Public S3 website URL for the dashboard."
  value       = "http://${aws_s3_bucket_website_configuration.dashboard.website_endpoint}"
}

output "kpi_api_lambda_arn" {
  description = "KPI API Lambda ARN."
  value       = aws_lambda_function.kpi_api.arn
}
