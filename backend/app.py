from flask import Flask, jsonify
import boto3
import psycopg2
import os
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# ------------------ PostgreSQL Connection ------------------
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

# ------------------ AWS Credentials ------------------
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# AWS Clients
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

# ------------------ Insert Functions ------------------
def insert_ec2(instance):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO ec2_instances (instance_id, instance_type, state, private_ip, public_ip, launch_time, region)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (instance_id) DO NOTHING
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
            ON CONFLICT (bucket_name) DO NOTHING
        """, (bucket["BucketName"], bucket["CreationDate"], AWS_REGION))
    conn.commit()

def insert_rds(db):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO rds_instances (db_instance_identifier, engine, status, allocated_storage, endpoint, port, creation_time, region)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (db_instance_identifier) DO NOTHING
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
            ON CONFLICT (user_id) DO NOTHING
        """, (
            user["UserName"], user["UserId"], user["Arn"], user["CreateDate"], user["PasswordLastUsed"]
        ))
    conn.commit()

# ------------------ Sync Route ------------------
@app.route('/api/fetch', methods=['POST'])
def fetch_and_store():
    # ===== EC2 =====
    aws_ec2_ids = []
    instances = ec2.describe_instances()
    for reservation in instances.get("Reservations", []):
        for inst in reservation.get("Instances", []):
            aws_ec2_ids.append(inst["InstanceId"])
            insert_ec2({
                "InstanceId": inst["InstanceId"],
                "InstanceType": inst["InstanceType"],
                "State": inst["State"]["Name"],
                "PrivateIP": inst.get("PrivateIpAddress"),
                "PublicIP": inst.get("PublicIpAddress"),
                "LaunchTime": inst["LaunchTime"].strftime("%Y-%m-%d %H:%M:%S")
            })
    with conn.cursor() as cur:
        cur.execute("SELECT instance_id FROM ec2_instances")
        db_ec2_ids = [row[0] for row in cur.fetchall()]
        for db_id in db_ec2_ids:
            if db_id not in aws_ec2_ids:
                cur.execute("DELETE FROM ec2_instances WHERE instance_id = %s", (db_id,))
    conn.commit()

    # ===== S3 =====
    aws_s3_names = []
    buckets = s3.list_buckets()
    for b in buckets.get("Buckets", []):
        aws_s3_names.append(b["Name"])
        insert_s3({
            "BucketName": b["Name"],
            "CreationDate": b["CreationDate"].strftime("%Y-%m-%d %H:%M:%S")
        })
    with conn.cursor() as cur:
        cur.execute("SELECT bucket_name FROM s3_buckets")
        db_s3_names = [row[0] for row in cur.fetchall()]
        for db_name in db_s3_names:
            if db_name not in aws_s3_names:
                cur.execute("DELETE FROM s3_buckets WHERE bucket_name = %s", (db_name,))
    conn.commit()

    # ===== RDS =====
    aws_rds_ids = []
    dbs = rds.describe_db_instances()
    for db in dbs.get("DBInstances", []):
        aws_rds_ids.append(db["DBInstanceIdentifier"])
        insert_rds({
            "DBInstanceIdentifier": db["DBInstanceIdentifier"],
            "Engine": db["Engine"],
            "Status": db["DBInstanceStatus"],
            "AllocatedStorage": db["AllocatedStorage"],
            "Endpoint": db.get("Endpoint", {}).get("Address"),
            "Port": db.get("Endpoint", {}).get("Port"),
            "CreationTime": db["InstanceCreateTime"].strftime("%Y-%m-%d %H:%M:%S")
        })
    with conn.cursor() as cur:
        cur.execute("SELECT db_instance_identifier FROM rds_instances")
        db_rds_ids = [row[0] for row in cur.fetchall()]
        for db_id in db_rds_ids:
            if db_id not in aws_rds_ids:
                cur.execute("DELETE FROM rds_instances WHERE db_instance_identifier = %s", (db_id,))
    conn.commit()

    # ===== IAM =====
    aws_iam_ids = []
    users = iam.list_users()
    for u in users.get("Users", []):
        aws_iam_ids.append(u["UserId"])
        insert_iam({
            "UserName": u["UserName"],
            "UserId": u["UserId"],
            "Arn": u["Arn"],
            "CreateDate": u["CreateDate"].strftime("%Y-%m-%d %H:%M:%S"),
            "PasswordLastUsed": u.get("PasswordLastUsed", None)
        })
    with conn.cursor() as cur:
        cur.execute("SELECT user_id FROM iam_users")
        db_iam_ids = [row[0] for row in cur.fetchall()]
        for db_id in db_iam_ids:
            if db_id not in aws_iam_ids:
                cur.execute("DELETE FROM iam_users WHERE user_id = %s", (db_id,))
    conn.commit()

    return jsonify({"status": "success", "message": "AWS data synced with DB (including deletions)"})


# ------------------ Services Route ------------------
@app.route('/api/services', methods=['GET'])
def get_services():
    data = {}
    with conn.cursor() as cur:
        for table in ["ec2_instances", "s3_buckets", "rds_instances", "iam_users"]:
            cur.execute(f"SELECT * FROM {table} ORDER BY created_at DESC")
            colnames = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            data[table] = [dict(zip(colnames, row)) for row in rows]
    return jsonify(data)


# ------------------ Run App ------------------
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
