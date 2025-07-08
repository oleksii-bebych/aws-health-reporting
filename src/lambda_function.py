import boto3
import os
import logging
from collections import defaultdict
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime

# Environment variables
SENDER = os.environ['email_from']
RECIPIENT = os.environ['email_to']
EMAIL_SUBJECT = "AWS Health Events Report"

# AWS clients
logger = logging.getLogger()
logger.setLevel(logging.INFO)
health = boto3.client('health', region_name='us-east-1')
org = boto3.client('organizations')
ses = boto3.client('ses', region_name='us-east-1')

def get_account_names():
    accounts = {}
    paginator = org.get_paginator('list_accounts')
    for page in paginator.paginate():
        for acct in page['Accounts']:
            accounts[acct['Id']] = acct['Name']
    return accounts

def get_health_events():
    events = []
    next_token = None
    while True:
        params = {
            'filter': {'eventStatusCodes': ['open', 'upcoming']},
            'maxResults': 50
        }
        if next_token:
            params['nextToken'] = next_token

        resp = health.describe_events_for_organization(**params)
        events.extend(resp.get('events', []))
        next_token = resp.get('nextToken')
        if not next_token:
            break
    return events

def get_event_description_org(event_arn, sample_account_id):
    try:
        response = health.describe_event_details_for_organization(
            organizationEventDetailFilters=[{
                'eventArn': event_arn,
                'awsAccountId': sample_account_id
            }]
        )
        details = response['successfulSet'][0]
        event = details['event']
        # Use detailed latestDescription if available
        description = details.get('eventDescription', {}).get('latestDescription') or event.get('description', 'No description')
        start_time = event.get('startTime', '')
        return description, start_time
    except Exception as e:
        logger.warning(f"Error fetching org event description for {event_arn}: {e}")
        return "No description", ''

def get_affected_entities(event, account_id):
    try:
        response = health.describe_affected_entities_for_organization(
            maxResults=50,
            organizationEntityAccountFilters=[{
                'eventArn': event['arn'],
                'awsAccountId': account_id,
                'statusCodes': ['IMPAIRED', 'UNIMPAIRED', 'UNKNOWN', 'PENDING']
            }]
        )
        return [e['entityValue'] for e in response.get('entities', [])]
    except Exception:
        return []

def generate_account_link(account_id):
    return f"https://health.aws.amazon.com/health/home#/account/{account_id}/events"

def lambda_handler(event, context):
    accounts = get_account_names()
    events = get_health_events()

    grouped = defaultdict(lambda: defaultdict(list))  # {(type, desc, time, arn, category): {entities: [accounts]}}

    for evt in events:
        event_type = evt['eventTypeCode']
        event_arn = evt['arn']
        category = evt.get("eventTypeCategory", "accountNotification")

        affected_accounts = health.describe_affected_accounts_for_organization(
            eventArn=event_arn)['affectedAccounts']

        if not affected_accounts:
            continue

        sample_account_id = affected_accounts[0]
        description, start_time = get_event_description_org(event_arn, sample_account_id)

        for account_id in affected_accounts:
            entities = get_affected_entities(evt, account_id)
            entity_signature = tuple(sorted(entities)) if entities else ("no entity", evt.get('region', 'N/A'))

            account_name = accounts.get(account_id, 'Unknown')
            account_link = generate_account_link(account_id)

            grouped[(event_type, description, start_time, event_arn, category)][entity_signature].append(
                f"<a href='{account_link}'>{account_id} - {account_name}</a>"
            )

    # HTML email body
    body = "<html><body style='font-family:Arial, sans-serif;'>"
    body += "<h2>AWS Health Events Report</h2>"

    category_paths = {
        "issue": "open-issues",
        "scheduledChange": "scheduled-changes",
        "accountNotification": "other-notifications"
    }

    for (event_type, description, start_time, event_arn, category), entity_groups in grouped.items():
        category_path = category_paths.get(category, "other-notifications")

        event_details_link = (
            f"https://health.console.aws.amazon.com/health/home"
            f"?region=us-east-1#/organization/dashboard/{category_path}"
            f"?eventID={event_arn}&eventTab=details"
        )

        body += f"<h3 style='color:#2c3e50;'>{event_type}</h3>"
        body += f"<p><b>Description:</b> {description}<br>"
        body += f"<b>Start Time:</b> {start_time.strftime('%Y-%m-%d %H:%M:%S') if isinstance(start_time, datetime) else start_time}<br>"
        body += f"<b>Event Details:</b> <a href='{event_details_link}' target='_blank'>{event_type}</a></p>"

        for entities, accounts_list in entity_groups.items():
            body += "<div style='margin-left:20px;'>"
            if isinstance(entities, tuple) and entities != ("no entity",):
                body += "<b>Affected Resources:</b><ul>"
                for ent in entities:
                    body += f"<li>{ent}</li>"
                body += "</ul>"
            else:
                body += f"<p><b>Affected Region:</b> {entities[1]}</p>"

            body += "<p><b>Affected Accounts:</b><ul>"
            for acct_html in accounts_list:
                body += f"<li>{acct_html}</li>"
            body += "</ul></p></div><hr style='margin:20px 0;'>"

    body += "</body></html>"

    # Send email via SES
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = EMAIL_SUBJECT
        msg['From'] = SENDER
        msg['To'] = RECIPIENT
        msg.attach(MIMEText(body, 'html'))

        ses.send_raw_email(
            Source=SENDER,
            Destinations=[RECIPIENT],
            RawMessage={'Data': msg.as_string()}
        )
        logger.info("Email sent successfully.")
    except Exception as e:
        logger.error(f"SES send failed: {e}")
