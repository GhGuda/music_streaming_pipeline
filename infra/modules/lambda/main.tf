# path.root is the env entrypoint (infra/envs/dev). The lambda source lives at
# the repo root under lambda/, so we go up three levels: envs/dev -> envs -> infra -> root.
data "archive_file" "archive_success_zip" {
  type        = "zip"
  source_file = "${path.root}/../../../lambda/archive_success/handler.py"
  output_path = "${path.root}/../../../lambda/archive_success/function.zip"
}

data "archive_file" "archive_failure_zip" {
  type        = "zip"
  source_file = "${path.root}/../../../lambda/archive_failure/handler.py"
  output_path = "${path.root}/../../../lambda/archive_failure/function.zip"
}

resource "aws_lambda_function" "archive_success" {
  function_name = "${var.name_prefix}-${var.environment}-archive-success"
  role          = var.lambda_role_arn
  runtime       = "python3.11"
  handler       = "handler.handler"
  filename      = data.archive_file.archive_success_zip.output_path
  source_code_hash = data.archive_file.archive_success_zip.output_base64sha256
  timeout       = 30

  environment {
    variables = {
      ARCHIVE_BUCKET = var.archive_bucket_name
    }
  }

  tags = merge(var.tags, {
    Name        = "${var.name_prefix}-${var.environment}-archive-success"
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}

resource "aws_lambda_function" "archive_failure" {
  function_name = "${var.name_prefix}-${var.environment}-archive-failure"
  role          = var.lambda_role_arn
  runtime       = "python3.11"
  handler       = "handler.handler"
  filename      = data.archive_file.archive_failure_zip.output_path
  source_code_hash = data.archive_file.archive_failure_zip.output_base64sha256
  timeout       = 30

  environment {
    variables = {
      ARCHIVE_BUCKET = var.archive_bucket_name
    }
  }

  tags = merge(var.tags, {
    Name        = "${var.name_prefix}-${var.environment}-archive-failure"
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}
