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
