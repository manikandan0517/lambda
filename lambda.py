import requests
import os
import json
import boto3
from botocore.exceptions import ClientError

def lambda_handler(event, context):
    try:
        route53 = boto3.client('route53')
        hosted_zone_id = os.environ.get("HOSTED_ZONE_ID")  # Environment variable for Hosted Zone ID
        record_name = os.environ.get("RECORD_NAME")  # Environment variable for DNS record name

        # Check if the DNS record exists
        if record_exists(route53, hosted_zone_id, record_name):
            message = f"Record {record_name} already exists."
            print(message)

            # Notify via email and Slack
            notify_via_ses("Record Exists Notification", message)
            notify_via_slack(message)

            return {
                "statusCode": 200,
                "body": json.dumps(message)
            }

        # Process Heroku and add CNAME record if it doesn't exist
        cname = process_heroku()
        add_cname_record(route53, hosted_zone_id, record_name, cname)

        return {
            "statusCode": 200,
            "body": json.dumps(f"CNAME record created for {record_name} pointing to {cname}.")
        }

    except Exception as e:
        error_message = f"An error occurred: {e}"
        print(error_message)

        # Notify via email and Slack
        notify_via_ses("Error Notification: Lambda Function", error_message)
        notify_via_slack(error_message)

        return {
            "statusCode": 500,
            "body": json.dumps(error_message)
        }

def notify_via_ses(subject, message):
    ses_client = boto3.client('ses', region_name="us-east-1")
    sender = os.environ.get("SENDER_EMAIL")  # Use environment variable for sender email
    recipient = os.environ.get("RECIPIENT_EMAIL")  # Use environment variable for recipient email

    try:
        ses_client.send_email(
            Source=sender,
            Destination={"ToAddresses": [recipient]},
            Message={
                "Subject": {"Data": subject},
                "Body": {"Text": {"Data": message}}
            }
        )
        print("Email notification sent successfully.")
    except ClientError as e:
        print(f"Error sending email notification: {e}")

def notify_via_slack(message):
    slack_webhook_url = os.environ.get('SLACK_WEBHOOK_URL')  # Slack webhook URL from environment
    payload = {"text": message}

    try:
        response = requests.post(slack_webhook_url, json=payload)
        response.raise_for_status()
        print("Slack notification sent successfully.")
    except requests.exceptions.RequestException as e:
        print(f"Error sending Slack notification: {e}")

def record_exists(route53, hosted_zone_id, record_name, record_type='CNAME'):
    try:
        response = route53.list_resource_record_sets(
            HostedZoneId=hosted_zone_id,
            StartRecordName=record_name,
            StartRecordType=record_type,
            MaxItems='1'
        )

        record_sets = response.get('ResourceRecordSets', [])
        if record_sets:
            record = record_sets[0]
            if record['Name'].rstrip('.') == record_name.rstrip('.') and record['Type'] == record_type:
                print(f"Record {record_name} of type {record_type} already exists.")
                return True

        print(f"Record {record_name} of type {record_type} does not exist.")
        return False

    except ClientError as e:
        print(f"Error checking for record: {e}")
        return False

def process_heroku():
    app_name = os.environ.get('APP_NAME')  # Heroku app name from environment
    hostname = os.environ.get('HOSTNAME')  # Hostname from environment
    api_token = os.environ.get('API_KEY')  # API token from environment
    certificate_name = os.environ.get('CERTIFICATE_NAME')  # Certificate name from environment

    url = f"https://api.heroku.com/apps/{app_name}/domains"

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.heroku+json; version=3",
    }

    payload = {
        "hostname": hostname,
        "sni_endpoint": certificate_name,
    }
    response = requests.post(url, json=payload, headers=headers)
    print(f"Status Code: {response.status_code}")

    if response.status_code != 201:
        raise Exception(f"Heroku API error: {response.text}")

    response_data = response.json()
    cname = response_data["cname"]
    print(f"CNAME: {cname}")
    return cname

def add_cname_record(route53, hosted_zone_id, record_name, cname_value):
    try:
        change_batch = {
            'Changes': [{
                'Action': 'CREATE',
                'ResourceRecordSet': {
                    'Name': record_name,
                    'Type': 'CNAME',
                    'TTL': 300,
                    'ResourceRecords': [{'Value': cname_value}]
                }
            }]
        }
        route53.change_resource_record_sets(
            HostedZoneId=hosted_zone_id,
            ChangeBatch=change_batch
        )
        print(f"CNAME record created for {record_name} pointing to {cname_value}")

    except route53.exceptions.InvalidChangeBatch as e:
        print(f"Error creating CNAME record: Record already exists. {e}")

    except ClientError as e:
        print(f"Error creating CNAME record: {e}")
