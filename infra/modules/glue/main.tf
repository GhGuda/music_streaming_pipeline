resource "aws_s3_object" "validate_script" {
  bucket = var.scripts_bucket_name
  key    = "glue/validate_inputs.py"
  source = "${path.root}/../../../glue_jobs/validate_inputs.py"
  etag   = filemd5("${path.root}/../../../glue_jobs/validate_inputs.py")
}

resource "aws_s3_object" "compute_script" {
  bucket = var.scripts_bucket_name
  key    = "glue/compute_kpis.py"
  source = "${path.root}/../../../glue_jobs/compute_kpis.py"
  etag   = filemd5("${path.root}/../../../glue_jobs/compute_kpis.py")
}

resource "aws_s3_object" "load_script" {
  bucket = var.scripts_bucket_name
  key    = "glue/load_dynamodb.py"
  source = "${path.root}/../../../glue_jobs/load_dynamodb.py"
  etag   = filemd5("${path.root}/../../../glue_jobs/load_dynamodb.py")
}

resource "aws_glue_job" "validate_inputs" {
  name     = "${var.name_prefix}-${var.environment}-validate-inputs"
  role_arn = var.glue_role_arn

  command {
    name            = "pythonshell"
    script_location = "s3://${var.scripts_bucket_name}/${aws_s3_object.validate_script.key}"
    python_version  = "3.9"
  }

  max_capacity = 1.0
  timeout      = 15

  default_arguments = {
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
  }

  tags = var.tags
}

resource "aws_glue_job" "compute_kpis" {
  name     = "${var.name_prefix}-${var.environment}-compute-kpis"
  role_arn = var.glue_role_arn

  command {
    name            = "glueetl"
    script_location = "s3://${var.scripts_bucket_name}/${aws_s3_object.compute_script.key}"
    python_version  = "3"
  }

  glue_version      = "4.0"
  worker_type       = "G.1X"
  number_of_workers = 2
  timeout           = 30

  default_arguments = {
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--raw_bucket"                       = var.raw_bucket_name
    "--processed_bucket"                 = var.processed_bucket_name
  }

  tags = var.tags
}

resource "aws_glue_job" "load_dynamodb" {
  name     = "${var.name_prefix}-${var.environment}-load-dynamodb"
  role_arn = var.glue_role_arn

  command {
    name            = "pythonshell"
    script_location = "s3://${var.scripts_bucket_name}/${aws_s3_object.load_script.key}"
    python_version  = "3.9"
  }

  max_capacity = 1.0
  timeout      = 15

  default_arguments = {
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--processed_bucket"                 = var.processed_bucket_name
    "--dynamodb_table"                   = var.dynamodb_table_name
  }

  tags = var.tags
}
