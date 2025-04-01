import boto3
import logging
from datetime import datetime
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

# Constants
OUTPUT_FILE_PATH = "/tmp/output.txt"
OBJECT_KEY = "output.txt"
SENDER = os.environ.get('email_from')
RECIPIENT = os.environ.get('email_to')
EMAIL_SUBJECT = "AWS Health Events Report"
# If needed to upload report to S3
BUCKET_NAME = os.environ.get('output_bucket')

# Set up logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Global clients
health_client = boto3.client('health', region_name='us-east-1')
s3_client = boto3.client('s3')
ses_client = boto3.client('ses', region_name='us-east-1')

def describe_health_events_for_organization():
    events = []
    next_token = None
    while True:
        params = {
            'filter': {
                'eventStatusCodes': ['open', 'upcoming']
            },
            'maxResults': 50
        }
        if next_token:
            params['nextToken'] = next_token

        try:
            response = health_client.describe_events_for_organization(**params)
        except Exception as e:
            logger.error("Failed to call describe_events_for_organization")
            logger.exception(e)
            raise

        events.extend(response.get('events', []))
        next_token = response.get('nextToken')
        if not next_token:
            break
    return events

def describe_health_events_details_for_organization(item, account_id):
    try:
        response = health_client.describe_event_details_for_organization(
            organizationEventDetailFilters=[
                {
                    'eventArn': item['arn'],
                    'awsAccountId': account_id
                }
            ]
        )
        return response
    except Exception as e:
        logger.error(f"Error getting event details: {e}")
        return {}

def describe_affected_accounts(item):
    try:
        response = health_client.describe_affected_accounts_for_organization(
            eventArn=item['arn'],
            maxResults=50
        )
        return response.get('affectedAccounts', [])
    except Exception as e:
        logger.error(f"Error getting affected accounts: {e}")
        return []

def describe_affected_entities(item, account_id):
    try:
        response = health_client.describe_affected_entities_for_organization(
            maxResults=50,
            organizationEntityAccountFilters=[
                {
                    'eventArn': item['arn'],
                    'awsAccountId': account_id,
                    'statusCodes': ['IMPAIRED', 'UNIMPAIRED', 'UNKNOWN', 'PENDING']
                }
            ]
        )
        return response.get('entities', [])
    except Exception as e:
        logger.error(f"Error getting affected entities: {e}")
        return []

def send_email_with_attachment():
    try:
        msg = MIMEMultipart()
        msg['Subject'] = EMAIL_SUBJECT
        msg['From'] = SENDER
        msg['To'] = RECIPIENT

        body = MIMEText("Please find attached the latest AWS Health Events report.", 'plain')
        msg.attach(body)

        with open(OUTPUT_FILE_PATH, 'rb') as file:
            attachment = MIMEApplication(file.read())
            attachment.add_header('Content-Disposition', 'attachment', filename=os.path.basename(OUTPUT_FILE_PATH))
            msg.attach(attachment)

        response = ses_client.send_raw_email(
            Source=SENDER,
            Destinations=[RECIPIENT],
            RawMessage={
                'Data': msg.as_string()
            }
        )
        logger.info("Email sent successfully.")
    except Exception as e:
        logger.error(f"Failed to send email: {e}")

def lambda_handler(event, context):
    health_events = describe_health_events_for_organization()
    affected_accounts_total = set()

    with open(OUTPUT_FILE_PATH, "a") as output_file:
        for item in health_events:
            output_file.write(f"\n{item['eventTypeCode']}\n")
            affected_accounts = describe_affected_accounts(item)
            for account in affected_accounts:
                affected_accounts_total.add(account)
                output_file.write(f"{account} - ")

                details = describe_health_events_details_for_organization(item, account)
                try:
                    event_info = details['successfulSet'][0]['event']
                    output_file.write(f"{event_info['startTime']} - ")
                except (IndexError, KeyError):
                    output_file.write("No details - ")
                    continue

                entities = describe_affected_entities(item, account)
                if not entities:
                    output_file.write(f"no entity - {event_info.get('region', 'N/A')}\n")
                else:
                    for entity in entities:
                        output_file.write(f"{entity['entityValue']}; ")
                    output_file.write(f"- {event_info.get('region', 'N/A')}\n")

        output_file.write("\n------------------\n")

        for account in affected_accounts_total:
            output_file.write(f"\n{account}\n")
            response = health_client.describe_events_for_organization(
                filter={
                    'awsAccountIds': [account],
                    'eventStatusCodes': ['open', 'upcoming']
                },
                maxResults=50
            )
            for event in response.get('events', []):
                entities = describe_affected_entities(event, account)
                time_str = event['startTime'].strftime("%m/%d/%Y, %H:%M:%S")
                region = event.get('region', 'N/A')
                if not entities:
                    output_file.write(f"{event['eventTypeCode']} - {time_str} - {region}\n")
                else:
                    for entity in entities:
                        output_file.write(f"{event['eventTypeCode']} - {time_str} - {entity['entityValue']} - {region}\n")

    try:
        s3_client.upload_file(OUTPUT_FILE_PATH, BUCKET_NAME, OBJECT_KEY)
        logger.info("Output file successfully uploaded to S3")
    except Exception as e:
        logger.error(f"Failed to upload file to S3: {e}")

    # Send file via email
    send_email_with_attachment()
