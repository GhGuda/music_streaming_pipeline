terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.5"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

locals {
  tags = {
    Project     = var.project_name
    Environment = var.environment
    Owner       = var.owner
    CostCenter  = var.cost_center
    ManagedBy   = "terraform"
  }
}

module "kms" {
  source      = "../../modules/kms"
  name_prefix = "${var.project_name}-${var.environment}"
  environment = var.environment
  tags        = local.tags
}

module "s3" {
  source      = "../../modules/s3"
  name_prefix = var.project_name
  environment = var.environment
  kms_key_arn = module.kms.key_arn
  tags        = local.tags
}

module "dynamodb" {
  source      = "../../modules/dynamodb"
  name_prefix = var.project_name
  environment = var.environment
  kms_key_arn = module.kms.key_arn
  tags        = local.tags
}

module "iam" {
  source                = "../../modules/iam"
  name_prefix           = var.project_name
  environment           = var.environment
  kms_key_arn           = module.kms.key_arn
  raw_bucket_name       = module.s3.raw_bucket_name
  processed_bucket_name = module.s3.processed_bucket_name
  archive_bucket_name   = module.s3.archive_bucket_name
  scripts_bucket_name   = module.s3.scripts_bucket_name
  dynamodb_table_arn    = module.dynamodb.table_arn
  tags                  = local.tags
}

module "lambda" {
  source              = "../../modules/lambda"
  name_prefix         = var.project_name
  environment         = var.environment
  lambda_role_arn     = module.iam.lambda_role_arn
  archive_bucket_name = module.s3.archive_bucket_name
  tags                = local.tags
}

module "step_functions" {
  source                  = "../../modules/step_functions"
  name_prefix             = var.project_name
  environment             = var.environment
  step_functions_role_arn = module.iam.step_functions_role_arn
  asl_template_path       = "${path.root}/../../state_machine/pipeline.asl.json"

  # Glue jobs are not yet provisioned in Terraform, so we wire deterministic names now.
  validate_job_name = "${var.project_name}-${var.environment}-validate-inputs"
  compute_job_name  = "${var.project_name}-${var.environment}-compute-kpis"
  load_job_name     = "${var.project_name}-${var.environment}-load-dynamodb"

  scripts_bucket      = module.s3.scripts_bucket_name
  raw_bucket          = module.s3.raw_bucket_name
  processed_bucket    = module.s3.processed_bucket_name
  dynamodb_table      = module.dynamodb.table_name
  archive_success_arn = module.lambda.archive_success_arn
  archive_failure_arn = module.lambda.archive_failure_arn
  tags                = local.tags
}

module "eventbridge" {
  source               = "../../modules/eventbridge"
  name_prefix          = var.project_name
  environment          = var.environment
  raw_bucket_name      = module.s3.raw_bucket_name
  state_machine_arn    = module.step_functions.state_machine_arn
  eventbridge_role_arn = module.iam.eventbridge_role_arn
  kms_key_arn          = module.kms.key_arn
  tags                 = local.tags
}
