output "ami_id" {
  description = "The ID of the custom AMI"
  value       = aws_ami_from_instance.ftp-to-s3-ami.id
}

output "instance_profile_arn" {
  description = "the arn of the instance profile"
  value       = aws_iam_instance_profile.ftp_to_s3_instance_role_profile.arn
}
output "instance_key_name" {
  description = "the arn of the instance profile"
  value       = aws_key_pair.generated_key.key_name
}