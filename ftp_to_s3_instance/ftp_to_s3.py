import ftplib
import math
import os
import socket
import sys
import threading
import time
from urllib.parse import urlparse

import boto3
import paramiko

S3_BUCKET_NAME = os.environ.get("S3_BUCKET_NAME")
PRODUCT_TABLE = os.environ.get("PRODUCTS_TABLE")
FTP_HOST = os.environ.get("FTP_HOST")
FTP_PATH = os.environ.get("FTP_PATH")
FTP_USERNAME = os.environ.get("FTP_USERNAME")
FTP_PASSWORD = os.environ.get("FTP_PASSWORD")

CHUNK_SIZE = 6291456


def setInterval(interval, times=-1):
    # This will be the actual decorator,
    # with fixed interval and times parameter
    def outer_wrap(function):
        # This will be the function to be
        # called
        def wrap(*args, **kwargs):
            stop = threading.Event()

            # This is another function to be executed
            # in a different thread to simulate setInterval
            def inner_wrap():
                i = 0
                while i != times and not stop.isSet():
                    stop.wait(interval)
                    function(*args, **kwargs)
                    i += 1

            t = threading.Timer(0, inner_wrap)
            t.daemon = True
            t.start()
            return stop

        return wrap

    return outer_wrap


class PyFTPclient:
    def __init__(self, host, path, port=21, login="anonymous", passwd="anonymous", monitor_interval=30):
        self.host = host
        self.port = port
        self.path = path
        self.login = login
        self.passwd = passwd
        self.monitor_interval = monitor_interval
        self.ptr = None
        self.max_attempts = 15
        self.waiting = True

    def downloadFile(self, fileObj):
        res = ""
        # open the file to write to and make a ptr
        print("DownloadFile {0}".format(fileObj))

        with open(fileObj["name"], "w+b") as f:
            self.ptr = f.tell()

            @setInterval(self.monitor_interval)
            def monitor():
                if not self.waiting:
                    i = f.tell()
                    if self.ptr < i:
                        # print("%d  -  %0.1f Kb/s" % (i, (i - self.ptr) / (1024 * self.monitor_interval)))
                        self.ptr = i
                    else:
                        ftp.close()

            def connect():
                ftp.connect(self.host, self.port)
                ftp.login(self.login, self.passwd)
                ftp.cwd(self.path)

                # optimize socket params for download task
                ftp.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
                ftp.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 75)
                ftp.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
                print("chunking ftp connected...")

            ftp = ftplib.FTP()
            ftp.set_debuglevel(2)
            ftp.set_pasv(True)

            connect()
            ftp.voidcmd("TYPE I")

            mon = monitor()
            while fileObj["size"] > f.tell():
                try:
                    connect()
                    print("Connected to folder: {0}".format(ftp.pwd()))
                    self.waiting = False
                    # retrieve file from position where we were disconnected
                    print("Getting file from position where we were disconnected...")
                    res = (
                        ftp.retrbinary("RETR %s" % fileObj["name"], f.write)
                        if f.tell() == 0
                        else ftp.retrbinary("RETR %s" % fileObj["name"], f.write, rest=f.tell())
                    )
                except:  # noqa E722
                    self.max_attempts -= 1
                    if self.max_attempts == 0:
                        mon.set()
                        print("")
                        raise
                    self.waiting = True
                    print("waiting 30 sec...")
                    time.sleep(30)
                    print("reconnect")

            mon.set()  # stop monitor
            ftp.close()

            if not res.startswith("226 Transfer complete"):
                print("Downloaded file {0} is not full.".format(fileObj["name"]))
                # os.remove(local_filename)
                return None

            return 1


def open_ftp_connection(ftp_url, ftp_path, username="", password="", auth_key=""):
    """
    Opens ftp connection and returns connection object

    """

    if "//" not in ftp_url:  # urlparse needs some kind of // in the url or it will think its a relative url
        ftp_url = "//" + ftp_url
    parsed_url = urlparse(ftp_url + ftp_path)
    print(
        "base url:{0}, user:{1}, pass:{2}, key:{3}, path: {4}".format(  # here for debugging....
            parsed_url.netloc, username, password, auth_key, parsed_url.path
        )
    )
    FTP_HOST = parsed_url.netloc  # update
    if auth_key == "":
        ftp_client = ftplib.FTP(FTP_HOST)
        ftp_client.login(username, password)
    else:
        ftp_client = ftplib.FTP_TLS(FTP_HOST)
        # auth key login
        # TODO
    if parsed_url.path != "":
        ftp_client.cwd(parsed_url.path)

    # optimize socket params for download task
    ftp_client.sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
    # ftp_client.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 75)
    # ftp_client.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
    print("FTP in folder: {0}".format(ftp_client.pwd()))
    return ftp_client


def open_sftp_connection(ftp_host, ftp_username="", ftp_password=""):
    """
    Opens sftp connection and returns connection object
    TODO doesn't work, paramiko isn't installed on the instance

    """
    client = paramiko.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ftp_connection = client.connect(
        ftp_host, username=ftp_username, password=ftp_password, look_for_keys=False, allow_agent=False
    )

    # try:
    # 	transport = paramiko.Transport(ftp_host)
    # except Exception as e:
    # 	print("Transport(ftp_host)", e)
    # 	return 'conn_error'
    # try:
    # 	transport.connect(username=ftp_username, password=ftp_password, look_for_keys=False, allow_agent=False)
    # except Exception as identifier:
    # 	print("Auth_error", identifier)
    # 	return 'auth_error'
    # ftp_connection = paramiko.SFTPClient.from_transport(transport)
    return ftp_connection


def transfer_chunk_from_ec2_to_s3(
    ftp_file, s3_connection, multipart_upload, bucket_name, s3_file_path, part_number, chunk_size
):

    # start_time = time.time()
    chunk = ftp_file.read(int(chunk_size))
    part = s3_connection.upload_part(
        Bucket=bucket_name,
        Key=s3_file_path,
        PartNumber=part_number,
        UploadId=multipart_upload["UploadId"],
        Body=chunk,
    )
    # end_time = time.time()
    # total_seconds = end_time - start_time
    # print(
    #     "speed is {} kb/s total seconds taken {}".format(
    #         math.ceil((int(chunk_size) / 1024) / total_seconds), total_seconds
    #     )
    # )
    part_output = {"PartNumber": part_number, "ETag": part["ETag"]}
    return part_output


def handleDownload(block, fileToWrite):
    print("Writing to file locallay!")
    fileToWrite.write(block)


def transfer_file_from_ftp_to_s3(bucket_name, ftp_file_obj, s3_file_path, ftp_client):

    s3_connection = boto3.client("s3")
    # ftp_file_size = ftp_file_obj["size"]
    # upload file in one gotry:
    try:
        with open(ftp_file_obj["name"], "wb") as fp:
            if ftp_file_obj["path"] != "":
                ftp_client.cwd(ftp_file_obj["path"])
            # print("FTP in folder: {0}".format(ftp_client.pwd()))
            ftp_client.retrbinary("RETR " + ftp_file_obj["name"], fp.write)
    except (NameError, ftplib.error_perm) as e:
        print("File could not be downloaded (does it still exist?) {0}, {1}".format(ftp_file_obj["name"], e))
        return
    with open(ftp_file_obj["name"], "rb") as ftp_file:
        if s3_file_path.endswith("/"):
            s3_file_path += ftp_file.name
        else:
            s3_file_path = s3_file_path + "/" + ftp_file.name
        print("Transferring {0} from FTP to S3 at {1}...".format(ftp_file.name, s3_file_path))
        s3_connection.upload_fileobj(ftp_file, bucket_name, s3_file_path)
        ftp_file.close()
    print("Successfully Transferred file from FTP to S3!")


def transfer_file_to_s3(bucket_name, ftp_file_obj, s3_file_path):
    print("Transferring File from EC2 to S3 in chunks...")
    if s3_file_path.endswith("/"):
        s3_file_path += ftp_file_obj["name"]
    else:
        s3_file_path = s3_file_path + "/" + ftp_file_obj["name"]
    # upload file in chunks
    s3_connection = boto3.client("s3")
    with open(ftp_file_obj["name"], "rb") as ftp_file:
        chunk_count = int(math.ceil(ftp_file_obj["size"] / float(CHUNK_SIZE)))
        multipart_upload = s3_connection.create_multipart_upload(Bucket=bucket_name, Key=s3_file_path)
        parts = []
        for i in range(chunk_count):
            # print("Transferring chunk {}...".format(i + 1))
            part = transfer_chunk_from_ec2_to_s3(
                ftp_file, s3_connection, multipart_upload, bucket_name, s3_file_path, i + 1, CHUNK_SIZE
            )
            parts.append(part)
            # print("Chunk {} Transferred Successfully!".format(i + 1))

        part_info = {"Parts": parts}
        s3_connection.complete_multipart_upload(
            Bucket=bucket_name, Key=s3_file_path, UploadId=multipart_upload["UploadId"], MultipartUpload=part_info
        )
        print("All chunks Transferred to S3 bucket! File Transfer successful!")
        ftp_file.close()


if __name__ == "__main__":
    s3_file_path = sys.argv[1]
    files_to_download = eval(sys.argv[2])
    if isinstance(files_to_download, dict):
        files_to_download = [files_to_download]
    print("*************VAR CHECK ******************")
    print(s3_file_path, files_to_download)
    print(FTP_HOST, FTP_PATH, FTP_USERNAME, FTP_PASSWORD)
    print(S3_BUCKET_NAME)
    print("*************VAR CHECK ******************")
    # todo deal with port numbers
    ftp_connection = open_ftp_connection(FTP_HOST, FTP_PATH, FTP_USERNAME, FTP_PASSWORD)
    if ftp_connection == "conn_error":
        print("Failed to connect FTP Server!")
    elif ftp_connection == "auth_error":
        print("Incorrect username or password!")
    else:
        for fileObj in files_to_download:
            ftpPath = FTP_PATH
            s3Path = s3_file_path
            if fileObj["path"] != "":
                ftpPath = FTP_PATH + fileObj["path"]
                s3Path = s3_file_path + fileObj["path"]
            print("Found File: {0}/{1} with size {2}".format(ftpPath, fileObj["name"], fileObj["size"]))

            fileObj["size"] = int(fileObj["size"])
            if fileObj["size"] <= int(CHUNK_SIZE):
                transfer_file_from_ftp_to_s3(S3_BUCKET_NAME, fileObj, s3Path, ftp_connection)
            else:
                # use wrapper to get large files
                # DownloadFile puts the file in local directory
                obj = PyFTPclient(FTP_HOST, ftpPath, port=ftplib.FTP_PORT, login=FTP_USERNAME, passwd=FTP_PASSWORD)
                obj.downloadFile(fileObj)
                transfer_file_to_s3(S3_BUCKET_NAME, fileObj, s3Path)
            # clean up file from system to free up space
            os.remove(fileObj["name"])
            # scanner updates etag when it finds the file in the holding bucket to trigger scanning
        print("Script complete.")
