import os

import boto3

AMI = os.environ["AMI"]
INSTANCE_TYPE = os.environ["INSTANCE_TYPE"]
KEY_NAME = os.environ["KEY_NAME"]
SUBNET_ID = os.environ["SUBNET_ID"]
REGION = os.environ["REGION"]
INSTANCE_PROFILE = os.environ["INSTANCE_PROFILE"]


ec2 = boto3.client("ec2", region_name=REGION)


def create_instance(event, files_to_download):
    """
    Using the event variables and the modified list of files to download create the ec2 instance to do the downloading
    """
    # convert to string with double quotes so it knows its a string
    files_to_download = ",".join(map('"{0}"'.format, files_to_download))
    vars = {
        "FTP_HOST": event["ftp_url"],
        "FTP_PATH": event["ftp_path"],
        "FTP_USERNAME": event["username"],
        "FTP_PASSWORD": event["password"],
        "FTP_AUTH_KEY": event["auth_key"],
        "S3_BUCKET_NAME": event["s3_bucket"],
        "PRODUCTS_TABLE": event["product_table"],
        "files_to_download": files_to_download,
        "s3_path": event["s3_path"],
    }
    print(vars)

    init_script = """#!/bin/bash
                /bin/echo "**************************"
                /bin/echo "* Running FTP to S3.     *"
                /bin/echo "**************************"
                /bin/pwd
                /bin/whoami
                export S3_BUCKET_NAME={S3_BUCKET_NAME}
                export PRODUCTS_TABLE={PRODUCTS_TABLE}
                export FTP_HOST={FTP_HOST}
                export FTP_PATH={FTP_PATH}
                export FTP_USERNAME={FTP_USERNAME}
                export FTP_PASSWORD={FTP_PASSWORD}
                /bin/echo python3 /home/ec2-user/ftp_to_s3.py {s3_path} {files_to_download}
                PYTHONUSERBASE=/home/ec2-user/.local python3.8 /home/ec2-user/ftp_to_s3.py {s3_path} {files_to_download}
                shutdown now -h""".format(
        **vars
    )

    instance = ec2.run_instances(
        ImageId=AMI,
        InstanceType=INSTANCE_TYPE,
        KeyName=KEY_NAME,
        SubnetId=SUBNET_ID,
        MaxCount=1,
        MinCount=1,
        InstanceInitiatedShutdownBehavior="terminate",
        UserData=init_script,
        IamInstanceProfile={"Arn": INSTANCE_PROFILE},
        BlockDeviceMappings=[{"DeviceName": "/dev/xvda", "Ebs": {"VolumeSize": 50}}],
    )

    instance_id = instance["Instances"][0]["InstanceId"]
    print("***New Instance! {0}***".format(instance_id))
    print("Instance downloading these files: {0}".format(files_to_download))
    return instance_id


def lambda_handler(event, context):
    # variables sent from scheduler.py
    print(event, context)

    # calculate files to download total size
    files_list = event["files_to_download"]

    total_size = 0
    size_limit = 30212254720  # set to 30GBish

    files_to_download = []
    for obj in files_list:
        total_size += int(obj["size"])
        if total_size < size_limit:
            files_to_download.append(obj)
        else:
            create_instance(event, files_to_download)
            files_to_download = [obj]
            total_size = int(obj["size"])
            # files_to_download.append(obj)

    create_instance(event, files_to_download)

    print("Finished.")
