terraform {
  required_version = ">= 1.6.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
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
