terraform {
  backend "s3" {
    # Fill these before running `terraform init` with remote state.
    # bucket         = "your-terraform-state-bucket"
    # key            = "music-streaming/dev/terraform.tfstate"
    # region         = "us-east-1"
    # dynamodb_table = "your-terraform-lock-table"
    # encrypt        = true
  }
}
