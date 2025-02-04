import os
import logging
import requests
import json
import boto3
from botocore.exceptions import ClientError
from datadog_api_client.v2 import ApiClient, ApiException, Configuration
from datadog_api_client.v2.api import logs_api
from datadog_api_client.v2.models import HTTPLog, HTTPLogItem
from dotenv import load_dotenv

load_dotenv()
class DDHandler(logging.StreamHandler):
    def __init__(self, configuration, service_name, ddsource):
        super().__init__()
        self.configuration = configuration
        self.service_name = service_name
        self.ddsource = ddsource

    def emit(self, record):
        msg = self.format(record)
        with ApiClient(self.configuration) as api_client:
            api_instance = logs_api.LogsApi(api_client)
            body = HTTPLog([
                HTTPLogItem(
                    ddsource=self.ddsource,
                    ddtags=f"env:{os.getenv('ENV', 'DEV')}",
                    message=msg,
                    service=self.service_name,
                )
            ])
            try:
                api_instance.submit_log(body)
            except ApiException as e:
                print(f"Error sending log: {e}")

class Logger:
    def __init__(self, service_name, ddsource):
        self.configuration = Configuration()
        self.logger = logging.getLogger("datadog_logger")
        self.logger.setLevel(logging.INFO)
        dd_handler = DDHandler(self.configuration, service_name, ddsource)
        dd_handler.setFormatter(logging.Formatter("%(message)s"))
        self.logger.addHandler(dd_handler)

    def log(self, message, level="info"):
        if level == "error":
            self.logger.error(message)
        else:
            self.logger.info(message)


os.environ["DD_API_KEY"] = os.environ.get("DATADOG_API_KEY")
os.environ["DD_SITE"] = "us5.datadoghq.com"
os.environ["ENV"] = "DEV"

logger = Logger(service_name="INSPECTPOINT-DNS-AUTOMATION", ddsource="python")



# AWS Route 53 Handling
def lambda_handler(event, context):
    route53 = boto3.client('route53')
    hosted_zone_id = os.environ.get('HOSTED_ZONE_ID')
    record_name = event.get('record')
    print(record_name)
    print(hosted_zone_id)

    try:
        if record_exists(route53, hosted_zone_id, record_name):
            message = f"Record {record_name} already exists."
            print(message)
            logger.log(message)
            return {"statusCode": 200, "body": json.dumps(message)}
        else:
            message = f"Record {record_name} does not exist."
            # cname=process_heroku()
            # if cname:
            #     add_cname_record(route53,hosted_zone_id,record_name,cname)

    except Exception as e:
        error_message = f"An error occurred: {str(e)}"
        logger.log(error_message, level="error")
        return {"statusCode": 500, "body": json.dumps({"error": error_message})}

def record_exists(route53, hosted_zone_id, record_name, record_type='CNAME'):
    try:
        response = route53.list_resource_record_sets(
            HostedZoneId=hosted_zone_id,
            StartRecordName=record_name,
            StartRecordType=record_type,
            MaxItems='1'
        )
        record_sets = response.get('ResourceRecordSets', [])
        print(record_sets)
        if record_sets and record_sets[0]['Name'].rstrip('.') == record_name.rstrip('.') and record_sets[0]['Type'] == record_type:
            return True
        return False

    except ClientError as e:
        error_message = f"Error checking for record in Route53: {e}"
        logger.log(error_message, level="error")
        return False
def process_heroku():
    try:
        app_name = os.environ.get('APP_NAME')
        hostname = os.environ.get('HOSTNAME')
        api_token = os.environ.get('API_KEY')
        certificate_name = os.environ.get('CERTIFICATE_NAME')

        url = f"https://api.heroku.com/apps/{app_name}/domains"
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.heroku+json; version=3",
        }

        payload = {"hostname": hostname, "sni_endpoint": certificate_name}
        response = requests.post(url, json=payload, headers=headers)

        if response.status_code != 201:
            error_message = f"Heroku API error: {response.text}"
            logger.log(error_message, level="error")
            raise Exception(error_message)

        response_data = response.json()
        cname = response_data["cname"]
        logger.log(f"Heroku CNAME: {cname}")
        return cname
    except Exception as e:
        error_message = f"Error processing Heroku domain: {str(e)}"
        logger.log(error_message, level="error")
        return None

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
        logger.log(f"CNAME record created for {record_name} pointing to {cname_value} in Route53")
    except route53.exceptions.InvalidChangeBatch as e:
        logger.log(f"Error creating CNAME record: Record already exists. {e}", level="error")
    except ClientError as e:
        logger.log(f"Error creating CNAME record in Route53: {e}", level="error")