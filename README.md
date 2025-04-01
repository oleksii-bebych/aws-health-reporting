# AWS Health reporting for AWS Organization

Configuration in this directory creates AWS Lambda Function, Permissions (IAM role) and EventBridge rule (scheduled).

## Prerequisites

1. Set up AWS Organizations. You must have an AWS organization with all features enabled.
2. Enable organizational view for AWS Health. After you set up AWS Organizations and sign in to the management account, you can enable AWS Health to aggregate all events. These events appear in the AWS Health Dashboard.
3. Register a Delegated Administrator for organizational view. You can register a member account in your AWS organization, which provides the flexibility for different teams to view and manage health events across your organization.
4. Apply the Terraform code in the Delegated Administrator account (region us-east-1)

## Usage

To run this example you need to execute:

```bash
$ terraform init
$ terraform plan
$ terraform apply
```

## Inputs
| Name | Description |
|------|-------------|
| email_from | Email FROM which the report will be sent via Amazon SES |
| email_to | Email TO which the report will be sent via Amazon SES |
| output_bucket_name | S3 bucket where to upload report to. If needed, MAKE SURE, S3 Bucket Policy allows s3:PutObject from the Lambda |