from flask import Flask, jsonify
import boto3
import psycopg2
import os
from flask_cors import CORS
from psycopg2 import sql

app = Flask(__name__)
CORS(app)

# ===== Database connection =====
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

# ===== AWS credentials =====
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# ===== AWS clients =====
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


def delete_not_in(table, column, valid_ids):
    with conn.cursor() as cur:
        if valid_ids:
            placeholders = ','.join(['%s'] * len(valid_ids))
            query = sql.SQL("DELETE FROM {table} WHERE {col} NOT IN ({ids})").format(
                table=sql.Identifier(table),
                col=sql.Identifier(column),
                ids=sql.SQL(placeholders)
            )
            cur.execute(query, valid_ids)
        else:
            # If no resources in AWS, clear table
            cur.execute(sql.SQL("DELETE FROM {table}").format(table=sql.Identifier(table)))
    conn.commit()


def sync_ec2():
    aws_ids = []
    instances = ec2.describe_instances()
    for reservation in instances.get("Reservations", []):
        for inst in reservation.get("Instances", []):
            aws_ids.append(inst["InstanceId"])
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO ec2_instances (instance_id, instance_type, state, private_ip, public_ip, launch_time, region)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (instance_id) DO NOTHING
                """, (
                    inst["InstanceId"], inst["InstanceType"], inst["State"]["Name"],
                    inst.get("PrivateIpAddress"), inst.get("PublicIpAddress"),
                    inst["LaunchTime"].strftime("%Y-%m-%d %H:%M:%S"), AWS_REGION
                ))
    delete_not_in("ec2_instances", "instance_id", aws_ids)


def sync_s3():
    aws_names = []
    buckets = s3.list_buckets()
    for b in buckets.get("Buckets", []):
        aws_names.append(b["Name"])
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO s3_buckets (bucket_name, creation_date, region)
                VALUES (%s, %s, %s)
                ON CONFLICT (bucket_name) DO NOTHING
            """, (
                b["Name"], b["CreationDate"].strftime("%Y-%m-%d %H:%M:%S"), AWS_REGION
            ))
    delete_not_in("s3_buckets", "bucket_name", aws_names)


def sync_rds():
    aws_ids = []
    dbs = rds.describe_db_instances()
    for db in dbs.get("DBInstances", []):
        aws_ids.append(db["DBInstanceIdentifier"])
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO rds_instances (db_instance_identifier, engine, status, allocated_storage, endpoint, port, creation_time, region)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (db_instance_identifier) DO NOTHING
            """, (
                db["DBInstanceIdentifier"], db["Engine"], db["DBInstanceStatus"], db["AllocatedStorage"],
                db.get("Endpoint", {}).get("Address"), db.get("Endpoint", {}).get("Port"),
                db["InstanceCreateTime"].strftime("%Y-%m-%d %H:%M:%S"), AWS_REGION
            ))
    delete_not_in("rds_instances", "db_instance_identifier", aws_ids)


def sync_iam():
    aws_ids = []
    users = iam.list_users()
    for u in users.get("Users", []):
        aws_ids.append(u["UserId"])
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO iam_users (user_name, user_id, arn, create_date, password_last_used)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO NOTHING
            """, (
                u["UserName"], u["UserId"], u["Arn"],
                u["CreateDate"].strftime("%Y-%m-%d %H:%M:%S"), u.get("PasswordLastUsed", None)
            ))
    delete_not_in("iam_users", "user_id", aws_ids)


@app.route('/api/fetch', methods=['POST'])
def fetch_and_store():
    sync_ec2()
    sync_s3()
    sync_rds()
    sync_iam()
    return jsonify({"status": "success", "message": "AWS data synced (added/removed) with DB"})


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


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
