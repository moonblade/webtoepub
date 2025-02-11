import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
import os
from utils import custom_logger

logger = custom_logger(__name__)

SENDER_EMAIL = os.getenv("SENDER_EMAIL", "")
APP_PASSWORD = os.getenv("APP_PASSWORD", "")
TO_EMAIL = os.getenv("TO_EMAIL", "")

def send_gmail(
    subject: str = "",
    content: str = "",
    attachment_path: str = "",
    sender_email: str = SENDER_EMAIL,
    app_password: str = APP_PASSWORD,
    to_email: str = TO_EMAIL
) -> bool:
    """
    Send an email with optional attachment using Gmail SMTP server.
    
    Args:
        sender_email (str): Your Gmail address
        app_password (str): Your Gmail app password (NOT your regular password)
        to_email (str): Recipient's email address
        subject (str): Email subject
        content (str): Email body content
        attachment_path (str, optional): Path to file to attach
        
    Returns:
        bool: True if email was sent successfully, False otherwise
        
    Raises:
        FileNotFoundError: If attachment file doesn't exist
        smtplib.SMTPException: If email sending fails
    """
    try:
        # Create message container
        msg = MIMEMultipart()
        msg['From'] = sender_email
        msg['To'] = to_email
        msg['Subject'] = subject

        # Add body
        msg.attach(MIMEText(content, 'plain'))

        # Add attachment if provided
        if attachment_path:
            if not os.path.exists(attachment_path):
                raise FileNotFoundError(f"Attachment file not found: {attachment_path}")
            
            with open(attachment_path, 'rb') as f:
                attachment = MIMEApplication(f.read(), _subtype=os.path.splitext(attachment_path)[1][1:])
                attachment.add_header(
                    'Content-Disposition', 
                    'attachment', 
                    filename=os.path.basename(attachment_path)
                )
                msg.attach(attachment)

        # Connect to Gmail SMTP server
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender_email, app_password)
            server.send_message(msg)
            
        return True

    except Exception as e:
        logger.exception(f"Failed to send email: {e}")
        return False

# Example usage:
"""
sender_email = "your.email@gmail.com"
app_password = "your-app-password"  # NOT your regular Gmail password
to_email = "recipient@example.com"
subject = "Test Email"
content = "This is a test email with attachment."
attachment_path = "path/to/your/file.pdf"  # Optional

success = send_gmail(
    sender_email=sender_email,
    app_password=app_password,
    to_email=to_email,
    subject=subject,
    content=content,
    attachment_path=attachment_path
)

if success:
    print("Email sent successfully!")
else:
    print("Failed to send email")
"""
