variable "email_from" {
  description = "Email FROM which the report will be sent via Amazon SES"
  type        = string
}

variable "email_to" {
  description = "Email TO which the report will be sent via Amazon SES"
  type        = string
}

variable "output_bucket_name" {
  description = "S3 bucket where to upload report to. If needed, MAKE SURE, S3 Bucket Policy allows s3:PutObject from the Lambda"
  type        = string
}
