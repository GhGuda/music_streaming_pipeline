resource "aws_dynamodb_table" "kpis" {
  name         = "${var.name_prefix}-${var.environment}-kpis"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  attribute {
    name = "gsi1pk"
    type = "S"
  }

  attribute {
    name = "gsi1sk"
    type = "S"
  }

  dynamic "global_secondary_index" {
    for_each = var.enable_gsi1 ? [1] : []
    content {
      name            = "gsi1"
      hash_key        = "gsi1pk"
      range_key       = "gsi1sk"
      projection_type = "ALL"
    }
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled     = true
    kms_key_arn = var.kms_key_arn
  }

  tags = merge(var.tags, {
    Name        = "${var.name_prefix}-${var.environment}-kpis"
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}
