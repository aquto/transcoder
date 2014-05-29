import time
from os import path
import urllib
import base64
import hmac
import hashlib
import pprint

from boto import elastictranscoder
from flask import Flask, request, render_template, jsonify


app = Flask(__name__)
app.config.from_object(__name__)

app.config.update(dict(
    DEBUG=True,
    AWS_REGION='us-east-1',
    AWS_ACCESS_KEY_ID=None,
    AWS_SECRET_ACCESS_KEY=None,
    ELASTIC_TRANSCODER_PIPELINE=None,
    S3_BASE_URL='s3.amazonaws.com',
    S3_BUCKET=None,
    S3_FOLDER=None
))
app.config.from_pyfile('/etc/transcoder/transcoder.conf', silent=True)
app.config.from_pyfile('transcoder.conf', silent=True)

AWS_REGION = app.config['AWS_REGION']
AWS_ACCESS_KEY_ID = app.config['AWS_ACCESS_KEY_ID']
AWS_SECRET_KEY = app.config['AWS_SECRET_ACCESS_KEY']
S3_BASE_URL = app.config['S3_BASE_URL']
S3_BUCKET_NAME = app.config['S3_BUCKET']
S3_BUCKET_URL = "//" + S3_BUCKET_NAME + "." + S3_BASE_URL
S3_FOLDER = app.config['S3_FOLDER'].strip('/')


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html", AWS_ACCESS_KEY_ID=AWS_ACCESS_KEY_ID, S3_BASE_URL=S3_BASE_URL, S3_BUCKET_NAME=S3_BUCKET_NAME, S3_BUCKET_URL=S3_BUCKET_URL,
                           S3_FOLDER=S3_FOLDER)


@app.route("/init_multipart", methods=["GET"])
def init_multipart():
    objectName = encodeURI(request.args.get("objectName"))

    url = "//{bucketName}.{s3BaseUrl}/{objectName}?uploads".format(
        bucketName=S3_BUCKET_NAME,
        s3BaseUrl=S3_BASE_URL,
        objectName=objectName
    )
    date = curdatetime()

    string = "POST\n\n\n\nx-amz-date:{date}\n/{bucketName}/{objectName}?uploads".format(
        date=date,
        bucketName=S3_BUCKET_NAME,
        objectName=objectName
    )
    signature = sign_string(string)
    authorization = "AWS " + AWS_ACCESS_KEY_ID + ":" + signature

    return jsonify({
        "url": url,
        "date": date,
        "authorization": authorization
    })


@app.route("/send_chunk", methods=["GET"])
def send_chunk():
    objectName = encodeURI(request.args.get("objectName"))
    partNumber = request.args.get("partNumber")
    uploadId = request.args.get("uploadId")
    contentMD5 = request.args.get("contentMD5")

    url = "//{bucketName}.{s3BaseUrl}/{objectName}?partNumber={partNumber}&uploadId={uploadId}".format(
        bucketName=S3_BUCKET_NAME,
        s3BaseUrl=S3_BASE_URL,
        objectName=objectName,
        partNumber=partNumber,
        uploadId=uploadId
    )
    date = curdatetime()

    string = "PUT\n{contentMD5}\n\n\nx-amz-date:{date}\n/{bucketName}/{objectName}?partNumber={partNumber}&uploadId={uploadId}".format(
        contentMD5=contentMD5,
        date=date,
        bucketName=S3_BUCKET_NAME,
        objectName=objectName,
        partNumber=partNumber,
        uploadId=uploadId
    )
    signature = sign_string(string)
    authorization = "AWS " + AWS_ACCESS_KEY_ID + ":" + signature

    return jsonify({
        "url": url,
        "date": date,
        "authorization": authorization
    })


@app.route("/complete_file", methods=["GET"])
def complete_file():
    objectName = encodeURI(request.args.get("objectName"))
    uploadId = request.args.get("uploadId")
    contentType = request.args.get("contentType")

    url = "//{bucketName}.{s3BaseUrl}/{objectName}?uploadId={uploadId}".format(
        bucketName=S3_BUCKET_NAME,
        s3BaseUrl=S3_BASE_URL,
        objectName=objectName,
        uploadId=uploadId
    )
    date = curdatetime()

    string = "POST\n\n{contentType}\n\nx-amz-date:{date}\n/{bucketName}/{objectName}?uploadId={uploadId}".format(
        contentType=contentType,
        date=date,
        bucketName=S3_BUCKET_NAME,
        objectName=objectName,
        uploadId=uploadId
    )
    signature = sign_string(string)
    authorization = "AWS " + AWS_ACCESS_KEY_ID + ":" + signature

    return jsonify({
        "url": url,
        "date": date,
        "authorization": authorization
    })


def encodeURI(uri_string):
    from urllib import quote

    return quote(uri_string, ";,/?:@&=+$!~*'()")


def curdatetime():
    return time.strftime("%a, %d %b %Y %H:%M:%S %Z", time.localtime()).strip()


def sign_string(string):
    return base64.b64encode(hmac.new(AWS_SECRET_KEY, string, hashlib.sha1).digest())


@app.route('/transcode/', methods=['POST', 'GET'])
def transcode():
    media_url = request.form['media_url']

    media_file = urllib.unquote(media_url).decode('utf8').rsplit('/', 1)[-1]

    transcode_input = {
        'Key': S3_FOLDER + '/' + media_file,
        'Container': 'auto',
        'AspectRatio': 'auto',
        'FrameRate': 'auto',
        'Resolution': 'auto',
        'Interlaced': 'auto'
    }

    transcode_outputs = [
        {
            'Key': path.splitext(media_file)[0],
            # iPhone4s
            'PresetId': '1351620000001-100020',
            'Rotate': 'auto',
            'ThumbnailPattern': 'thumbnail-{count}'
        }
    ]

    transcode = elastictranscoder.connect_to_region(AWS_REGION, aws_access_key_id=AWS_ACCESS_KEY_ID,
                                                    aws_secret_access_key=AWS_SECRET_KEY)
    pipeline_id = None
    for pipeline in transcode.list_pipelines()['Pipelines']:
        if pipeline['Name'] == app.config['ELASTIC_TRANSCODER_PIPELINE']:
            pipeline_id = pipeline['Id']

    job = transcode.create_job(pipeline_id=pipeline_id, input_name=transcode_input, outputs=transcode_outputs, output_key_prefix=S3_FOLDER + '/')

    pp = pprint.PrettyPrinter(indent=4)

    return render_template('transcode.html', job=pp.pformat(job))


if __name__ == '__main__':
    app.run()
