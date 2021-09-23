#TODO
# add s3 and dynamo permissions
# cloudwatch trigger every 5 min

resource "aws_iam_role" "iam_for_instance_invoke" {
  name = "iam_for_instance_invoke_lambda_permissions_${var.suffix}"

  assume_role_policy = <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Action": "sts:AssumeRole",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Effect": "Allow"
    }
  ]
}
EOF
}

resource "aws_iam_policy" "iam_for_instance_invoke" {
  name = "instance_access_policy_${var.suffix}"

  policy = <<EOF
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "logs:CreateLogGroup",
                "logs:CreateLogStream",
                "logs:PutLogEvents"
            ],
            "Resource": "arn:aws:logs:*:*:*"
        },
        {
            "Action": [
                "ec2:RunInstances"
            ],
            "Effect": "Allow",
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": "iam:PassRole",
            "Resource": "*"
        },
        {
            "Effect": "Allow",
            "Action": "iam:ListInstanceProfiles",
            "Resource": "*"
        }
    ]
}
EOF
}

resource "aws_iam_role_policy_attachment" "instance_s3_role" {
  role       = aws_iam_role.iam_for_instance_invoke.name
  policy_arn = aws_iam_policy.iam_for_instance_invoke.arn
}

resource "aws_iam_role_policy_attachment" "ftp_to_s3_instance_invoke_write_logs" {
  role       = aws_iam_role.iam_for_instance_invoke.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "ftp_to_s3_instance_invoke_read_logs" {
  role       = aws_iam_role.iam_for_instance_invoke.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Wire CloudWatch logging policy to role
resource "aws_iam_role_policy_attachment" "log_policy" {
  role       = aws_iam_role.iam_for_instance_invoke.name
  policy_arn = "arn:aws:iam::aws:policy/CloudWatchAgentServerPolicy"
}
# DB write access (unsure if still needed)




data "archive_file" "ftp_to_s3_instance_invoke" {
  type = "zip"
  source {
    content  = file("${path.module}/functions/ftp_to_s3_instance_invoke.py")
    filename = "ftp_to_s3_instance_invoke.py"
  }
  output_path = "./.lambdas/ftp_to_s3_instance_invoke.zip"
}


resource "aws_lambda_function" "ftp_to_s3_instance_invoke" {
  function_name    = "warpgate_ftp_to_s3_instance_invoke_${var.suffix}"
  filename         = data.archive_file.ftp_to_s3_instance_invoke.output_path
  source_code_hash = data.archive_file.ftp_to_s3_instance_invoke.output_base64sha256
  description      = "Handles creating ec2 instance for downloading ftp and moving to s3"
  handler          = "ftp_to_s3_instance_invoke.lambda_handler"
  runtime          = "python3.8"
  memory_size      = "128"
  timeout          = 900
  role             = aws_iam_role.iam_for_instance_invoke.arn


  environment {
    variables = {
      AMI              = var.ami
      INSTANCE_TYPE    = var.instance_type
      KEY_NAME         = var.key_name
      SUFFIX           = var.suffix
      SUBNET_ID        = var.subnet_id
      REGION           = var.region
      INSTANCE_PROFILE = var.instance_profile_arn
    }
  }

}