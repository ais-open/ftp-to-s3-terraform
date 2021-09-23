output "arn" {
  value       = "${aws_lambda_function.ftp_to_s3_instance_invoke.qualified_arn}"
  description = "Lambda's ARN"
}