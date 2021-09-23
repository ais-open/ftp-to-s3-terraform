variable "ami" {
  description = "AMI of the custom instance created for FTP."
  type        = string
  default     = ""
}

variable "instance_type" {
  description = "instance type of the ami given"
  type        = string
  default     = ""
}
variable "instance_profile_arn" {
  description = "instance profile arn of the ami given"
  type        = string
  default     = ""
}

variable "key_name" {
  description = "Name the key to use for security."
  type        = string
  default     = ""
}

variable "subnet_id" {
  description = "subnet id to be used"
  type        = string
  default     = ""
}

variable "region" {
  description = "aws region"
}

variable "suffix" {
  description = "Unique suffix to apply to all resources. Used to deconflict resources within same account."
}