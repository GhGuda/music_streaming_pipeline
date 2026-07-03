resource "aws_sns_topic" "alerts" {
  name = "${var.name_prefix}-${var.environment}-alerts"
  tags = var.tags
}

resource "aws_sns_topic_subscription" "alerts_email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

resource "aws_cloudwatch_metric_alarm" "sfn_failed" {
  alarm_name          = "${var.name_prefix}-${var.environment}-sfn-failed"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "ExecutionsFailed"
  namespace           = "AWS/States"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "Step Functions execution failures detected"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  dimensions = {
    StateMachineArn = var.state_machine_arn
  }
  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "sfn_timed_out" {
  alarm_name          = "${var.name_prefix}-${var.environment}-sfn-timeout"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "ExecutionsTimedOut"
  namespace           = "AWS/States"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "Step Functions execution timeouts detected"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  dimensions = {
    StateMachineArn = var.state_machine_arn
  }
  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "lambda_archive_success_errors" {
  alarm_name          = "${var.name_prefix}-${var.environment}-lambda-archive-success-errors"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "archive_success Lambda returned errors"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  dimensions = {
    FunctionName = var.archive_success_function_name
  }
  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "lambda_archive_failure_errors" {
  alarm_name          = "${var.name_prefix}-${var.environment}-lambda-archive-failure-errors"
  comparison_operator = "GreaterThanOrEqualToThreshold"
  evaluation_periods  = 1
  metric_name         = "Errors"
  namespace           = "AWS/Lambda"
  period              = 300
  statistic           = "Sum"
  threshold           = 1
  alarm_description   = "archive_failure Lambda returned errors"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  dimensions = {
    FunctionName = var.archive_failure_function_name
  }
  tags = var.tags
}

resource "aws_cloudwatch_metric_alarm" "eventbridge_dlq_visible" {
  alarm_name          = "${var.name_prefix}-${var.environment}-eventbridge-dlq-visible"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 300
  statistic           = "Maximum"
  threshold           = 0
  alarm_description   = "EventBridge DLQ has pending messages"
  alarm_actions       = [aws_sns_topic.alerts.arn]
  dimensions = {
    QueueName = var.eventbridge_dlq_name
  }
  tags = var.tags
}
