from flask import Flask, jsonify
import boto3
import psycopg2
import os

app = Flask(__name__)

# PostgreSQL connection
DB_HOST = os.getenv("HOST", "postgres")
DB_NAME = os.getenv("POSTGRES_DB", "awsdb")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "password")

conn = psycopg2.connect(
    host=DB_HOST,
    database=DB_NAME,
    user=DB_USER,
    password=DB_PASS
)

# AWS credsentials
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# AWS clients
ec2 = boto3.client('ec2', region_name=AWS_REGION,
                   aws_access_key_id=AWS_ACCESS_KEY,
                   aws_secret_access_key=AWS_SECRET_KEY)
s3 = boto3.client('s3', region_name=AWS_REGION,
                  aws_access_key_id=AWS_ACCESS_KEY,
                  aws_secret_access_key=AWS_SECRET_KEY)
rds = boto3.client('rds', region_name=AWS_REGION,
                   aws_access_key_id=AWS_ACCESS_KEY,
                   aws_secret_access_key=AWS_SECRET_KEY)
iam = boto3.client('iam', region_name=AWS_REGION,
                   aws_access_key_id=AWS_ACCESS_KEY,
                   aws_secret_access_key=AWS_SECRET_KEY)


def insert_service(service_name, details):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO aws_services (service_name, details) VALUES (%s, %s)",
            (service_name, details)
        )
    conn.commit()

@app.route('/fetch', methods=['POST'])
def fetch_and_store():
    # EC2
    instances = ec2.describe_instances()
    insert_service("EC2", str(instances))

    # S3
    buckets = s3.list_buckets()
    insert_service("S3", str(buckets))

    # RDS
    dbs = rds.describe_db_instances()
    insert_service("RDS", str(dbs))

    # IAM
    users = iam.list_users()
    insert_service("IAM", str(users))

    return jsonify({"status": "success", "message": "AWS data stored in DB"})

@app.route('/services', methods=['GET'])
def get_services():
    with conn.cursor() as cur:
        cur.execute("SELECT id, service_name, details, created_at FROM aws_services ORDER BY created_at DESC")
        rows = cur.fetchall()
    return jsonify([
        {"id": r[0], "service_name": r[1], "details": r[2], "created_at": str(r[3])}
        for r in rows
    ])

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)