# Pull the current account ID to suffix bucket names so they're globally unique
# without depending on someone else's `music-streaming-dev-*` never being taken.
data "aws_caller_identity" "current" {}

locals {
  base_tags = merge(var.tags, {
    Environment = var.environment
    ManagedBy   = "terraform"
  })

  account_suffix = data.aws_caller_identity.current.account_id
  bucket_base    = "${var.name_prefix}-${var.environment}"
}

# force_destroy = true lets `terraform destroy` empty versioned buckets
# (including non-current object versions and delete markers) without manual cleanup.
# Disable this if you ever care about preventing accidental data loss.
resource "aws_s3_bucket" "raw" {
  bucket        = "${local.bucket_base}-raw-${local.account_suffix}"
  force_destroy = var.force_destroy_buckets
  tags          = merge(local.base_tags, { Name = "${local.bucket_base}-raw-${local.account_suffix}" })
}

resource "aws_s3_bucket" "processed" {
  bucket        = "${local.bucket_base}-processed-${local.account_suffix}"
  force_destroy = var.force_destroy_buckets
  tags          = merge(local.base_tags, { Name = "${local.bucket_base}-processed-${local.account_suffix}" })
}

resource "aws_s3_bucket" "archive" {
  bucket        = "${local.bucket_base}-archive-${local.account_suffix}"
  force_destroy = var.force_destroy_buckets
  tags          = merge(local.base_tags, { Name = "${local.bucket_base}-archive-${local.account_suffix}" })
}

resource "aws_s3_bucket" "scripts" {
  bucket        = "${local.bucket_base}-scripts-${local.account_suffix}"
  force_destroy = var.force_destroy_buckets
  tags          = merge(local.base_tags, { Name = "${local.bucket_base}-scripts-${local.account_suffix}" })
}

resource "aws_s3_bucket_public_access_block" "raw" {
  bucket                  = aws_s3_bucket.raw.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Publish S3 Object Created / Deleted events to the default EventBridge bus.
# Without this, the EventBridge rule that triggers Step Functions never receives
# any events from this bucket.
resource "aws_s3_bucket_notification" "raw_eventbridge" {
  bucket      = aws_s3_bucket.raw.id
  eventbridge = true
}

resource "aws_s3_bucket_public_access_block" "processed" {
  bucket                  = aws_s3_bucket.processed.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "archive" {
  bucket                  = aws_s3_bucket.archive.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_public_access_block" "scripts" {
  bucket                  = aws_s3_bucket.scripts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "raw" {
  bucket = aws_s3_bucket.raw.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_versioning" "processed" {
  bucket = aws_s3_bucket.processed.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_versioning" "archive" {
  bucket = aws_s3_bucket.archive.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_versioning" "scripts" {
  bucket = aws_s3_bucket.scripts.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "raw" {
  bucket = aws_s3_bucket.raw.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "processed" {
  bucket = aws_s3_bucket.processed.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "archive" {
  bucket = aws_s3_bucket.archive.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "scripts" {
  bucket = aws_s3_bucket.scripts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}
