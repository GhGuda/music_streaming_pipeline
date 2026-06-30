resource "aws_sqs_queue" "eb_dlq" {
  name                      = "${var.name_prefix}-${var.environment}-eb-dlq"
  kms_master_key_id         = var.kms_key_arn
  message_retention_seconds = 1209600
  tags                      = var.tags
}

resource "aws_sqs_queue_policy" "eb_dlq_policy" {
  queue_url = aws_sqs_queue.eb_dlq.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowEventBridgeSend"
        Effect    = "Allow"
        Principal = { Service = "events.amazonaws.com" }
        Action    = "sqs:SendMessage"
        Resource  = aws_sqs_queue.eb_dlq.arn
      }
    ]
  })
}

resource "aws_cloudwatch_event_rule" "stream_upload" {
  name        = "${var.name_prefix}-${var.environment}-stream-upload"
  description = "Trigger pipeline on new stream CSV uploads"
  # IMPORTANT: items in a key matcher array are OR'd. The previous version
  # was `[{prefix = "incoming/streams/"}, {suffix = ".csv"}]` which matched
  # ANY .csv anywhere in the bucket (including incoming/users/users.csv and
  # incoming/songs/songs.csv) — those got mistakenly fed into the pipeline,
  # failed validation, and were moved to archive/failed/ by the failure
  # Lambda. The wildcard matcher below ANDs prefix and suffix into a single
  # condition so dimension files don't trigger the pipeline.
  event_pattern = jsonencode({
    source      = ["aws.s3"]
    detail-type = ["Object Created"]
    detail = {
      bucket = { name = [var.raw_bucket_name] }
      object = { key = [{ wildcard = "incoming/streams/*.csv" }] }
    }
  })
  tags = var.tags
}

resource "aws_cloudwatch_event_target" "to_sfn" {
  rule     = aws_cloudwatch_event_rule.stream_upload.name
  arn      = var.state_machine_arn
  role_arn = var.eventbridge_role_arn

  dead_letter_config {
    arn = aws_sqs_queue.eb_dlq.arn
  }

  retry_policy {
    maximum_event_age_in_seconds = 3600
    maximum_retry_attempts       = 4
  }
}
