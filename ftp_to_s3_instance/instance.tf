# build out an instance with python 3.8, the corect libs and our python script
# this may require setting up an instance with ssh
# then create an ami of that instance


# Generate a ssh key that lives in terraform
# https://registry.terraform.io/providers/hashicorp/tls/latest/docs/resources/private_key
resource "tls_private_key" "instance_private_key" {
  algorithm = "RSA"
  rsa_bits  = 4096
}
 
resource "aws_key_pair" "instance_key_pair" {
  key_name   = "${var.key_name}"
  public_key = "${tls_private_key.instance_private_key.public_key_openssh}"
 
}


resource "aws_security_group" "instance_sg" {
  name   = "allow-all-sg"
  vpc_id = "${var.vpc_id}"

  ingress {
    description = "ftp port"
    cidr_blocks = ["0.0.0.0/0"]
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
  }
}



#iam instance profile setup
# Create an IAM role for the Web Servers.
#iam instance profile setup
resource "aws_iam_role" "instance_s3_access_iam_role" {
  name               = "instance_s3_access_iam_role"
  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": "sts:AssumeRole",
      "Principal": {
        "Service": "ec2.amazonaws.com"
      },
      "Effect": "Allow",
      "Sid": ""
    }
  ]
}
EOF
}
resource "aws_iam_policy" "iam_policy_for_ftp_to_s3_instance" {
  name = "ftp_to_s3_access_policy"
 
  policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "VisualEditor0",
      "Effect": "Allow",
      "Action": [
          "s3:PutObject",
          "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::${var.s3_bucket}"
  },
}
EOF
}
 
resource "aws_iam_role_policy_attachment" "ftp_to_s3" {
  role       = aws_iam_role.instance_s3_access_iam_role.name
  policy_arn = aws_iam_policy.iam_policy_for_ftp_to_s3_instance.arn
}
 
resource "aws_iam_instance_profile" "ftp_to_s3_instance_profile" {
  name = "ftp_to_s3_instance_profile"
  role = "instance_s3_access_iam_role"
}


# Instance that we want to build out
resource "aws_instance" "ftp-to-s3-instance" {
  ami           = var.ami
  instance_type = var.instance_type
  subnet_id     = var.subnet_id
  key_name     = "${var.key_name}" #use your own key for testing
  security_groups      = ["${aws_security_group.instance_sg.id}"]
  iam_instance_profile = "${aws_iam_instance_profile.ftp_to_s3_instance_profile.id}"
 
  # Copies the python file to /home/ec2-user
  # depending on how the install of python works we may need to change this location
  connection {
    type        = "ssh"
    user        = "ec2-user"
    host        = "${element(aws_instance.ftp-to-s3-instance.*.public_ip, 0)}"
    private_key = "${tls_private_key.instance_private_key.private_key_pem}"
  }
 
  provisioner "file" {
    source      = "${path.module}/ftp_to_s3.py"
    destination = "/home/ec2-user/ftp_to_s3.py"
  }
   
  user_data = <<EOF
#!/bin/sh
sudo amazon-linux-extras install python3.8
python3.8 -m pip install -U pip
pip3.8 --version
pip3.8 install boto3 
pip3.8 install paramiko 
 
EOF
}

# ## Creating that copy of the instance for use by the lambda


resource "aws_ami_from_instance" "ftp-to-s3-ami" {
  name               = "ftp-to-s3_ami"
  description        = "ftp transfer to s3 bucket python 3.8 script"
  source_instance_id = "${aws_instance.ftp-to-s3-instance.id}"
 
  depends_on = [aws_instance.ftp-to-s3-instance]
 
  tags = {
    Name = "ftp-to-s3-ami"
  }
}