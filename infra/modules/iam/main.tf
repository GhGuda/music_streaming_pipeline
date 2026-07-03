data "aws_iam_policy_document" "glue_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["glue.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "lambda_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "step_functions_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["states.amazonaws.com"]
    }
  }
}

data "aws_iam_policy_document" "eventbridge_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }
  }
}

locals {
  policy_vars = {
    kms_key_arn         = var.kms_key_arn
    raw_bucket_name     = var.raw_bucket_name
    processed_bucket    = var.processed_bucket_name
    archive_bucket      = var.archive_bucket_name
    scripts_bucket      = var.scripts_bucket_name
    dynamodb_table_arn  = var.dynamodb_table_arn
  }
}

resource "aws_iam_role" "glue" {
  name               = "${var.name_prefix}-${var.environment}-glue-role"
  assume_role_policy = data.aws_iam_policy_document.glue_assume.json
  tags               = var.tags
}

resource "aws_iam_role" "lambda" {
  name               = "${var.name_prefix}-${var.environment}-lambda-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume.json
  tags               = var.tags
}

resource "aws_iam_role" "step_functions" {
  name               = "${var.name_prefix}-${var.environment}-step-functions-role"
  assume_role_policy = data.aws_iam_policy_document.step_functions_assume.json
  tags               = var.tags
}

resource "aws_iam_role" "eventbridge" {
  name               = "${var.name_prefix}-${var.environment}-eventbridge-role"
  assume_role_policy = data.aws_iam_policy_document.eventbridge_assume.json
  tags               = var.tags
}

resource "aws_iam_policy" "glue" {
  name   = "${var.name_prefix}-${var.environment}-glue-policy"
  policy = templatefile("${path.module}/policies/glue_policy.json", local.policy_vars)
}

resource "aws_iam_policy" "lambda" {
  name   = "${var.name_prefix}-${var.environment}-lambda-policy"
  policy = templatefile("${path.module}/policies/lambda_policy.json", local.policy_vars)
}

resource "aws_iam_policy" "step_functions" {
  name   = "${var.name_prefix}-${var.environment}-step-functions-policy"
  policy = templatefile("${path.module}/policies/step_functions_policy.json", local.policy_vars)
}

resource "aws_iam_policy" "eventbridge" {
  name   = "${var.name_prefix}-${var.environment}-eventbridge-policy"
  policy = templatefile("${path.module}/policies/eventbridge_policy.json", local.policy_vars)
}

resource "aws_iam_role_policy_attachment" "glue" {
  role       = aws_iam_role.glue.name
  policy_arn = aws_iam_policy.glue.arn
}

resource "aws_iam_role_policy_attachment" "lambda" {
  role       = aws_iam_role.lambda.name
  policy_arn = aws_iam_policy.lambda.arn
}

resource "aws_iam_role_policy_attachment" "step_functions" {
  role       = aws_iam_role.step_functions.name
  policy_arn = aws_iam_policy.step_functions.arn
}

resource "aws_iam_role_policy_attachment" "eventbridge" {
  role       = aws_iam_role.eventbridge.name
  policy_arn = aws_iam_policy.eventbridge.arn
}
