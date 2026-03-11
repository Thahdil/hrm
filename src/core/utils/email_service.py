import requests
import logging

logger = logging.getLogger(__name__)

def send_external_email(sender_name, recipient_emails, subject, body):
    """
    Sends an email using the external construction API.
    """
    url = "https://api.construction.salonsyncs.com/api/send-email"
    payload = {
        "from": f"EONS HRM - {sender_name}",
        "to": recipient_emails,
        "subject": subject,
        "body": body
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info(f"Email sent successfully to {recipient_emails}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {recipient_emails}: {str(e)}")
        return False
