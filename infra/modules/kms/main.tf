resource "aws_kms_key" "data" {
  description             = "${var.name_prefix} data encryption key"
  deletion_window_in_days = 7
  enable_key_rotation     = true

  tags = merge(var.tags, {
    Name        = "${var.name_prefix}-data-key"
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}

resource "aws_kms_alias" "data" {
  name          = "alias/${var.name_prefix}-data-key"
  target_key_id = aws_kms_key.data.key_id
}
