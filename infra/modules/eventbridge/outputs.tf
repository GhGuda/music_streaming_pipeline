output "event_rule_name" {
  description = "EventBridge rule name for stream uploads."
  value       = aws_cloudwatch_event_rule.stream_upload.name
}

output "eventbridge_dlq_arn" {
  description = "DLQ ARN for EventBridge target delivery failures."
  value       = aws_sqs_queue.eb_dlq.arn
}

output "eventbridge_dlq_url" {
  description = "DLQ URL for EventBridge target delivery failures."
  value       = aws_sqs_queue.eb_dlq.id
}
