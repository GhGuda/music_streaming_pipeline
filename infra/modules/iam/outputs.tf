output "glue_role_arn" {
  description = "Glue execution role ARN."
  value       = aws_iam_role.glue.arn
}

output "lambda_role_arn" {
  description = "Lambda execution role ARN."
  value       = aws_iam_role.lambda.arn
}

output "step_functions_role_arn" {
  description = "Step Functions execution role ARN."
  value       = aws_iam_role.step_functions.arn
}

output "eventbridge_role_arn" {
  description = "EventBridge target role ARN."
  value       = aws_iam_role.eventbridge.arn
}
