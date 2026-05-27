locals {
  state_machine_definition = templatefile(var.asl_template_path, {
    validate_job_name   = var.validate_job_name
    compute_job_name    = var.compute_job_name
    load_job_name       = var.load_job_name
    scripts_bucket      = var.scripts_bucket
    raw_bucket          = var.raw_bucket
    processed_bucket    = var.processed_bucket
    dynamodb_table      = var.dynamodb_table
    archive_success_arn = var.archive_success_arn
    archive_failure_arn = var.archive_failure_arn
  })
}

resource "aws_sfn_state_machine" "pipeline" {
  name       = "${var.name_prefix}-${var.environment}-pipeline"
  role_arn   = var.step_functions_role_arn
  definition = local.state_machine_definition

  tags = merge(var.tags, {
    Name        = "${var.name_prefix}-${var.environment}-pipeline"
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}
