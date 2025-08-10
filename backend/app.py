from flask import Flask, jsonify
import boto3
import psycopg2
import os
from flask_cors import CORS


app = Flask(__name__)
#CORS(app)
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

# AWS credentials
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


# Insert functions for each service
def insert_ec2(instance):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO ec2_instances (instance_id, instance_type, state, private_ip, public_ip, launch_time, region)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            instance["InstanceId"], instance["InstanceType"], instance["State"],
            instance["PrivateIP"], instance["PublicIP"], instance["LaunchTime"], AWS_REGION
        ))
    conn.commit()

def insert_s3(bucket):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO s3_buckets (bucket_name, creation_date, region)
            VALUES (%s, %s, %s)
        """, (bucket["BucketName"], bucket["CreationDate"], AWS_REGION))
    conn.commit()

def insert_rds(db):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO rds_instances (db_instance_identifier, engine, status, allocated_storage, endpoint, port, creation_time, region)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            db["DBInstanceIdentifier"], db["Engine"], db["Status"], db["AllocatedStorage"],
            db["Endpoint"], db["Port"], db["CreationTime"], AWS_REGION
        ))
    conn.commit()

def insert_iam(user):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO iam_users (user_name, user_id, arn, create_date, password_last_used)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            user["UserName"], user["UserId"], user["Arn"], user["CreateDate"], user["PasswordLastUsed"]
        ))
    conn.commit()


@app.route('/fetch', methods=['POST'])
def fetch_and_store():
    # EC2
    instances = ec2.describe_instances()
    for reservation in instances.get("Reservations", []):
        for inst in reservation.get("Instances", []):
            insert_ec2({
                "InstanceId": inst["InstanceId"],
                "InstanceType": inst["InstanceType"],
                "State": inst["State"]["Name"],
                "PrivateIP": inst.get("PrivateIpAddress"),
                "PublicIP": inst.get("PublicIpAddress"),
                "LaunchTime": inst["LaunchTime"].strftime("%Y-%m-%d %H:%M:%S")
            })

    # S3
    buckets = s3.list_buckets()
    for b in buckets.get("Buckets", []):
        insert_s3({
            "BucketName": b["Name"],
            "CreationDate": b["CreationDate"].strftime("%Y-%m-%d %H:%M:%S")
        })

    # RDS
    dbs = rds.describe_db_instances()
    for db in dbs.get("DBInstances", []):
        insert_rds({
            "DBInstanceIdentifier": db["DBInstanceIdentifier"],
            "Engine": db["Engine"],
            "Status": db["DBInstanceStatus"],
            "AllocatedStorage": db["AllocatedStorage"],
            "Endpoint": db.get("Endpoint", {}).get("Address"),
            "Port": db.get("Endpoint", {}).get("Port"),
            "CreationTime": db["InstanceCreateTime"].strftime("%Y-%m-%d %H:%M:%S")
        })

    # IAM
    users = iam.list_users()
    for u in users.get("Users", []):
        insert_iam({
            "UserName": u["UserName"],
            "UserId": u["UserId"],
            "Arn": u["Arn"],
            "CreateDate": u["CreateDate"].strftime("%Y-%m-%d %H:%M:%S"),
            "PasswordLastUsed": u.get("PasswordLastUsed", None)
        })

    return jsonify({"status": "success", "message": "AWS data stored in separate tables"})


@app.route('/services', methods=['GET'])
def get_services():
    data = {}
    with conn.cursor() as cur:
        for table in ["ec2_instances", "s3_buckets", "rds_instances", "iam_users"]:
            cur.execute(f"SELECT * FROM {table} ORDER BY created_at DESC")
            colnames = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            data[table] = [dict(zip(colnames, row)) for row in rows]
    return jsonify(data)


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
