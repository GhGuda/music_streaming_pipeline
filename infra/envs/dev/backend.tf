# Backend defaults to LOCAL state.
# The state file is written to ./terraform.tfstate (gitignored).
#
# Local state is fine while a single person is iterating from their machine.
# Switch to remote S3 state when ANY of these become true:
#   - more than one person needs to run terraform
#   - CI/CD (cd.yml) needs to apply changes
#   - the state file needs to survive a laptop loss
#
# To migrate: uncomment the block below, fill the four values, then run
#   terraform init -migrate-state
#
# terraform {
#   backend "s3" {
#     bucket         = "your-terraform-state-bucket"
#     key            = "music-streaming/dev/terraform.tfstate"
#     region         = "us-east-1"
#     dynamodb_table = "your-terraform-lock-table"
#     encrypt        = true
#   }
# }
