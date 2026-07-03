data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

locals {
  bucket_name = "${var.name_prefix}-${var.environment}-dashboard-${data.aws_caller_identity.current.account_id}"
  api_name    = "${var.name_prefix}-${var.environment}-kpi-api"
  source_root = "${path.root}/../../../dashboard"
}

data "archive_file" "kpi_api_zip" {
  type        = "zip"
  source_file = "${path.root}/../../../lambda/kpi_api/handler.py"
  output_path = "${path.root}/../../../lambda/kpi_api/function.zip"
}

resource "aws_lambda_function" "kpi_api" {
  function_name    = "${var.name_prefix}-${var.environment}-kpi-api"
  role             = var.lambda_role_arn
  runtime          = "python3.11"
  handler          = "handler.handler"
  filename         = data.archive_file.kpi_api_zip.output_path
  source_code_hash = data.archive_file.kpi_api_zip.output_base64sha256
  timeout          = 15

  environment {
    variables = {
      DYNAMODB_TABLE = var.dynamodb_table_name
      CORS_ORIGIN    = "*"
    }
  }

  tags = merge(var.tags, {
    Name        = "${var.name_prefix}-${var.environment}-kpi-api"
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}

resource "aws_apigatewayv2_api" "kpi" {
  name          = local.api_name
  protocol_type = "HTTP"

  cors_configuration {
    allow_headers = ["content-type"]
    allow_methods = ["GET", "OPTIONS"]
    allow_origins = ["*"]
    max_age       = 3600
  }

  tags = var.tags
}

resource "aws_apigatewayv2_integration" "kpi_lambda" {
  api_id                 = aws_apigatewayv2_api.kpi.id
  integration_type       = "AWS_PROXY"
  integration_uri        = aws_lambda_function.kpi_api.invoke_arn
  payload_format_version = "2.0"
}

resource "aws_apigatewayv2_route" "routes" {
  for_each = toset([
    "GET /dates",
    "GET /daily",
    "GET /top-genres",
    "GET /top-songs",
  ])

  api_id    = aws_apigatewayv2_api.kpi.id
  route_key = each.value
  target    = "integrations/${aws_apigatewayv2_integration.kpi_lambda.id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.kpi.id
  name        = "$default"
  auto_deploy = true

  tags = var.tags
}

resource "aws_lambda_permission" "api_gateway" {
  statement_id  = "AllowExecutionFromApiGateway"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.kpi_api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.kpi.execution_arn}/*/*"
}

resource "aws_s3_bucket" "dashboard" {
  bucket        = local.bucket_name
  force_destroy = true

  tags = merge(var.tags, {
    Name        = local.bucket_name
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}

resource "aws_s3_bucket_ownership_controls" "dashboard" {
  bucket = aws_s3_bucket.dashboard.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "dashboard" {
  bucket                  = aws_s3_bucket.dashboard.id
  block_public_acls       = true
  block_public_policy     = false
  ignore_public_acls      = true
  restrict_public_buckets = false
}

resource "aws_s3_bucket_website_configuration" "dashboard" {
  bucket = aws_s3_bucket.dashboard.id

  index_document {
    suffix = "index.html"
  }
}

resource "aws_s3_bucket_policy" "dashboard_public_read" {
  bucket = aws_s3_bucket.dashboard.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "PublicReadDashboardAssets"
        Effect    = "Allow"
        Principal = "*"
        Action    = "s3:GetObject"
        Resource  = "${aws_s3_bucket.dashboard.arn}/*"
      }
    ]
  })

  depends_on = [aws_s3_bucket_public_access_block.dashboard]
}

resource "aws_s3_object" "index" {
  bucket       = aws_s3_bucket.dashboard.id
  key          = "index.html"
  source       = "${local.source_root}/index.html"
  etag         = filemd5("${local.source_root}/index.html")
  content_type = "text/html"
}

resource "aws_s3_object" "styles" {
  bucket       = aws_s3_bucket.dashboard.id
  key          = "styles.css"
  source       = "${local.source_root}/styles.css"
  etag         = filemd5("${local.source_root}/styles.css")
  content_type = "text/css"
}

resource "aws_s3_object" "app" {
  bucket       = aws_s3_bucket.dashboard.id
  key          = "app.js"
  source       = "${local.source_root}/app.js"
  etag         = filemd5("${local.source_root}/app.js")
  content_type = "application/javascript"
}

resource "aws_s3_object" "config" {
  bucket       = aws_s3_bucket.dashboard.id
  key          = "config.js"
  content      = templatefile("${local.source_root}/config.js.tpl", { api_base_url = aws_apigatewayv2_api.kpi.api_endpoint })
  content_type = "application/javascript"
  etag         = md5(templatefile("${local.source_root}/config.js.tpl", { api_base_url = aws_apigatewayv2_api.kpi.api_endpoint }))
}
