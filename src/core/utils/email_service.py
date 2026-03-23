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
        error_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
            error_msg += f" | Response: {e.response.text}"
        logger.error(f"Failed to send email to {recipient_emails}: {error_msg}")
        print(f"EMAIL_DEBUG: {error_msg}")
        return False
