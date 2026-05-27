output "alerts_topic_arn" {
  description = "SNS topic ARN used by alarms."
  value       = aws_sns_topic.alerts.arn
}

output "sfn_failed_alarm_name" {
  description = "Alarm name for Step Functions failures."
  value       = aws_cloudwatch_metric_alarm.sfn_failed.alarm_name
}

output "eventbridge_dlq_alarm_name" {
  description = "Alarm name for EventBridge DLQ depth."
  value       = aws_cloudwatch_metric_alarm.eventbridge_dlq_visible.alarm_name
}
