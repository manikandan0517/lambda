import requests
import os
import json
import boto3
from botocore.exceptions import ClientError
from datadog import initialize, api

# Initialize Datadog
options = {
    'api_key': 'c75de666fc0996b7091c427b415e99ebc875a766',
    'app_key': '13d53b92-f236-49a1-9792-0133d59df97e',
}
initialize(**options)

def send_error_to_datadog(title, error_message, tags=None):
    """
    Sends an error event and metric to Datadog.
    
    :param title: Title of the error event
    :param error_message: Description of the error
    :param tags: List of tags to include with the event and metric
    """
    if tags is None:
        tags = []
    
    try:
        # Send error event to Datadog
        api.Event.create(
            title=title,
            text=error_message,
            tags=tags,
            alert_type="error"
        )
        print("Error event sent to Datadog.")
        
        # Send error metric to Datadog
        api.Metric.send(
            metric="lambda.function.error",
            points=1,
            tags=tags
        )
        print("Error metric sent to Datadog.")
    except Exception as e:
        print(f"Failed to send error to Datadog: {e}")


def lambda_handler(event, context):
    route53 = boto3.client('route53')
    hosted_zone_id = os.environ.get("HOSTED_ZONE_ID")  # Environment variable for Hosted Zone ID
    record_name = event.get('record')  # DNS record name from event

    try:
        # Check if the DNS record exists
        if record_exists(route53, hosted_zone_id, record_name):
            message = f"Record {record_name} already exists."
            print(message)
            send_error_to_datadog(
            title="Lambda Function Error",
            error_message=message,
            tags=["lambda", "error", f"function:{context.function_name}"]
        )

            # # Notify via Slack
            # notify_via_slack(message)

            # return {
            #     "statusCode": 200,
            #     "body": json.dumps(message)
            # }

        # # Process Heroku and add CNAME record if it doesn't exist
        # cname = process_heroku()
        # add_cname_record(route53, hosted_zone_id, record_name, cname)

        # return {
        #     "statusCode": 200,
        #     "body": json.dumps(f"CNAME record created for {record_name} pointing to {cname}.")
        # }

    except Exception as e:
        error_message = f"An error occurred: {str(e)}"
        print(f"e:{error_message}")

        # Use the reusable Datadog error function
        send_error_to_datadog(
            title="Lambda Function Error",
            error_message=error_message,
            tags=["lambda", "error", f"function:{context.function_name}"]
        )

        return {
            "statusCode": 500,
            "body": json.dumps({"error": error_message})
        }


def notify_via_slack(message):
    slack_webhook_url = os.environ.get('SLACK_WEBHOOK_URL')
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
