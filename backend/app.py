# app.py
from flask import Flask, jsonify, request
import boto3
import psycopg2
import os
from flask_cors import CORS
from psycopg2 import sql
import logging
from botocore.exceptions import NoCredentialsError, ClientError

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# ===== Database connection (adjust env vars as needed) =====
DB_HOST = os.getenv("HOST", "postgres")
DB_NAME = os.getenv("POSTGRES_DB", "awsdb")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "password")

try:
    conn = psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )
    conn.autocommit = False
except Exception as e:
    log.exception("Failed to connect to Postgres. Check DB env vars and network.")
    raise

# ===== AWS credentials & helper to create clients =====
AWS_ACCESS_KEY = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")


def make_client(service):
    kwargs = {"region_name": AWS_REGION}
    if AWS_ACCESS_KEY and AWS_SECRET_KEY:
        kwargs.update({
            "aws_access_key_id": AWS_ACCESS_KEY,
            "aws_secret_access_key": AWS_SECRET_KEY
        })
    # If creds not provided explicitly, boto3 will try instance profile / env / shared config
    return boto3.client(service, **kwargs)


ec2 = make_client("ec2")
s3 = make_client("s3")
rds = make_client("rds")
iam = make_client("iam")


# ===== Utility: delete rows not in AWS list (safe for empty lists) =====
def delete_not_in(table, column, valid_ids):
    with conn.cursor() as cur:
        if valid_ids:
            placeholders = ",".join(["%s"] * len(valid_ids))
            query = sql.SQL("DELETE FROM {table} WHERE {col} NOT IN ({ids})").format(
                table=sql.Identifier(table),
                col=sql.Identifier(column),
                ids=sql.SQL(placeholders)
            )
            cur.execute(query, valid_ids)
        else:
            # No resources in AWS -> clear table
            cur.execute(sql.SQL("DELETE FROM {table}").format(table=sql.Identifier(table)))
    conn.commit()
    log.info("Sync deletion finished for %s (column %s). Kept %d items.", table, column, len(valid_ids))


# ===== Sync functions (upsert + delete missing) =====
def sync_ec2():
    aws_ids = []
    paginator = ec2.get_paginator("describe_instances")
    for page in paginator.paginate():
        for reservation in page.get("Reservations", []):
            for inst in reservation.get("Instances", []):
                instance_id = inst.get("InstanceId")
                aws_ids.append(instance_id)

                launch_time = None
                if inst.get("LaunchTime"):
                    try:
                        launch_time = inst["LaunchTime"].strftime("%Y-%m-%d %H:%M:%S")
                    except Exception:
                        launch_time = str(inst.get("LaunchTime"))

                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO ec2_instances (instance_id, instance_type, state, private_ip, public_ip, launch_time, region)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (instance_id) DO UPDATE
                        SET instance_type = EXCLUDED.instance_type,
                            state = EXCLUDED.state,
                            private_ip = EXCLUDED.private_ip,
                            public_ip = EXCLUDED.public_ip,
                            launch_time = EXCLUDED.launch_time,
                            region = EXCLUDED.region
                    """, (
                        instance_id,
                        inst.get("InstanceType"),
                        inst.get("State", {}).get("Name"),
                        inst.get("PrivateIpAddress"),
                        inst.get("PublicIpAddress"),
                        launch_time,
                        AWS_REGION
                    ))
    delete_not_in("ec2_instances", "instance_id", aws_ids)
    conn.commit()
    log.info("EC2 sync done. Count from AWS: %d", len(aws_ids))


def sync_s3():
    aws_names = []
    # list_buckets returns all buckets for the account; region is not provided per-bucket here
    try:
        buckets = s3.list_buckets()
    except ClientError as e:
        log.exception("Failed to list S3 buckets.")
        raise
    for b in buckets.get("Buckets", []):
        name = b.get("Name")
        aws_names.append(name)
        creation_date = None
        if b.get("CreationDate"):
            try:
                creation_date = b["CreationDate"].strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                creation_date = str(b.get("CreationDate"))

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO s3_buckets (bucket_name, creation_date, region)
                VALUES (%s, %s, %s)
                ON CONFLICT (bucket_name) DO UPDATE
                SET creation_date = EXCLUDED.creation_date,
                    region = EXCLUDED.region
            """, (name, creation_date, AWS_REGION))
    delete_not_in("s3_buckets", "bucket_name", aws_names)
    conn.commit()
    log.info("S3 sync done. Count from AWS: %d", len(aws_names))


def sync_rds():
    aws_ids = []
    paginator = rds.get_paginator("describe_db_instances")
    for page in paginator.paginate():
        for db in page.get("DBInstances", []):
            identifier = db.get("DBInstanceIdentifier")
            aws_ids.append(identifier)

            creation_time = None
            if db.get("InstanceCreateTime"):
                try:
                    creation_time = db["InstanceCreateTime"].strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    creation_time = str(db.get("InstanceCreateTime"))

            endpoint = db.get("Endpoint", {}) or {}
            endpoint_addr = endpoint.get("Address")
            endpoint_port = endpoint.get("Port")

            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO rds_instances (db_instance_identifier, engine, status, allocated_storage, endpoint, port, creation_time, region)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (db_instance_identifier) DO UPDATE
                    SET engine = EXCLUDED.engine,
                        status = EXCLUDED.status,
                        allocated_storage = EXCLUDED.allocated_storage,
                        endpoint = EXCLUDED.endpoint,
                        port = EXCLUDED.port,
                        creation_time = EXCLUDED.creation_time,
                        region = EXCLUDED.region
                """, (
                    identifier, db.get("Engine"), db.get("DBInstanceStatus"), db.get("AllocatedStorage"),
                    endpoint_addr, endpoint_port, creation_time, AWS_REGION
                ))
    delete_not_in("rds_instances", "db_instance_identifier", aws_ids)
    conn.commit()
    log.info("RDS sync done. Count from AWS: %d", len(aws_ids))


def sync_iam():
    aws_ids = []
    paginator = iam.get_paginator("list_users")
    for page in paginator.paginate():
        for u in page.get("Users", []):
            user_id = u.get("UserId")
            aws_ids.append(user_id)
            create_date = None
            if u.get("CreateDate"):
                try:
                    create_date = u["CreateDate"].strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    create_date = str(u.get("CreateDate"))

            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO iam_users (user_name, user_id, arn, create_date, password_last_used)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (user_id) DO UPDATE
                    SET user_name = EXCLUDED.user_name,
                        arn = EXCLUDED.arn,
                        create_date = EXCLUDED.create_date,
                        password_last_used = EXCLUDED.password_last_used
                """, (
                    u.get("UserName"), user_id, u.get("Arn"), create_date, u.get("PasswordLastUsed")
                ))
    delete_not_in("iam_users", "user_id", aws_ids)
    conn.commit()
    log.info("IAM sync done. Count from AWS: %d", len(aws_ids))


# ===== API routes =====
@app.route("/api/fetch", methods=["POST"])
def fetch_and_store():
    try:
        # run all syncs; each will commit its changes and delete missing rows
        sync_ec2()
        sync_s3()
        sync_rds()
        sync_iam()
        return jsonify({"status": "success", "message": "AWS data synced (added/updated/removed) with DB"}), 200
    except NoCredentialsError:
        log.exception("AWS credentials missing")
        return jsonify({"status": "error", "message": "AWS credentials missing; ensure env vars or instance role is available"}), 500
    except Exception as e:
        log.exception("Sync failed")
        return jsonify({"status": "error", "message": "Sync failed", "detail": str(e)}), 500


@app.route("/api/services", methods=["GET"])
def get_services():
    data = {}
    with conn.cursor() as cur:
        for table in ["ec2_instances", "s3_buckets", "rds_instances", "iam_users"]:
            cur.execute(sql.SQL("SELECT * FROM {t}").format(t=sql.Identifier(table)))
            colnames = [desc[0] for desc in cur.description]
            rows = cur.fetchall()
            data[table] = [dict(zip(colnames, row)) for row in rows]
    return jsonify(data)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
