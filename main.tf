provider "aws" {
  region = "us-east-1"

  # Make it faster by skipping something
  #skip_metadata_api_check     = true
  skip_region_validation      = true
  skip_credentials_validation = true
}

module "eventbridge" {
  source = "terraform-aws-modules/eventbridge/aws"

  create_bus = false

  rules = {
    crons = {
      description         = "Trigger for a Lambda"
      schedule_expression = "rate(1 day)"
    }
  }

  targets = {
    crons = [
      {
        name  = "lambda-loves-cron"
        arn   = module.lambda_function.lambda_function_arn
        input = jsonencode({"job": "cron-by-rate"})
      }
    ]
  }
}

module "lambda_function" {
  source = "terraform-aws-modules/lambda/aws"

  function_name = "aws-health-regular-check"
  description   = "Daily report about AWS Health events"
  handler       = "lambda_function.lambda_handler"
  runtime       = "python3.13"
  timeout       = 300

  source_path = "./src/"

  environment_variables = {
    email_from      = var.email_from
    email_to        = var.email_to
    output_bucket   = var.output_bucket_name
  }

  create_current_version_allowed_triggers = false
  allowed_triggers = {
    OneRule = {
      principal  = "events.amazonaws.com"
      source_arn = module.eventbridge.eventbridge_rule_arns["crons"]
    }
  }

   attach_policy_statements = true
   policy_statements = {
     aws_health = {
       effect    = "Allow",
       actions   = [
        "health:DescribeEventsForOrganization", 
        "health:DescribeEventDetails",
        "health:DescribeEventDetailsForOrganization",
        "health:DescribeAffectedAccountsForOrganization",
        "health:DescribeAffectedEntitiesForOrganization"
        ],
       resources = ["*"]
     },
     organizations = {
       effect    = "Allow",
       actions   = ["organizations:ListAccounts"],
       resources = ["*"]
     },
     s3 = {
       effect    = "Allow",
       actions   = ["s3:PutObject"],
       resources = ["arn:aws:s3:::${var.output_bucket_name}/*"]
     },
    ses = {
       effect    = "Allow",
       actions   = ["ses:SendRawEmail"],
       resources = [
            aws_ses_email_identity.email_from.arn, 
            aws_ses_email_identity.email_to.arn
       ]
    }
   }

  tags = {
    Name = "aws-health-regular-check"
  }
}

### An identity is a email address you use to send email through Amazon SES. Identity verification at the domain level extends to all email addresses under one verified domain identity. To verify ownership of an email address, you must have access to its inbox to open the verification email.

resource "aws_ses_email_identity" "email_from" {
  email = var.email_from
}

resource "aws_ses_email_identity" "email_to" {
  email = var.email_to
}