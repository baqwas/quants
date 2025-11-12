import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage # Assuming this is used for attachments


SENDER_EMAIL = "iot_admi@parkcircus.org"
RECIPIENT_EMAIL = "reza@parkcircus.org"
SMTP_SERVER = "bezaman.parkcircus.org"
SMTP_PORT = 587 # SMTP_STARTTLS typically uses port 587
SMTP_PASSWORD = "ApnaChabee!"

message = MIMEMultipart('alternative')
message['Subject'] = "Hello SMTP Test"
message['From'] = SENDER_EMAIL
message['To'] = RECIPIENT_EMAIL

"""

msg_related = MIMEMultipart('related')
message.attach(msg_related)

# ... (Your text_content and html_content generation code) ...

msg_text = MIMEText(text_content, 'plain')
msg_related.attach(msg_text)

# ... (Your HTML content generation and image attachment code) ...

msg_html = MIMEText(html_content, 'html')
msg_related.attach(msg_html)

message.attach(msg_related)

"""

try:
    # 1. Establish connection and initiate TLS
    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        try:
            # SMTP-SSL/TLS: port 465
            # SMTP-STARTTLS: port 587
            server.starttls()
        except smtplib.SMTPException as e:
            print(f"SMTP Error during STARTTLS negotiation: {e}. \nCheck server's TLS support or port:{SMTP_PORT}.")
            exit(-1)

        # 2. Authenticate
        try:
            server.login(SENDER_EMAIL, SMTP_PASSWORD)
        except smtplib.SMTPAuthenticationError as e:
            print(f"SMTP Authentication Error: {e}. \nUsername<{SENDER_EMAIL}> password<{SMTP_PASSWORD}>")
            exit(-2)
        except smtplib.SMTPRecipientsRefused as e:
            print(f"SMTP Error: Server refused recipients during login (unusual, but possible if configured): {e}")
            exit(-3)
        except smtplib.SMTPSenderRefused as e:
            print(f"SMTP Error: Server refused sender during login (unusual, but possible if configured): {e}")
            exit(-4)
        except smtplib.SMTPDataError as e:
            print(f"SMTP Error: Unexpected data error during login: {e}")
            exit(-5)
        except smtplib.SMTPException as e:
            print(f"Generic SMTP Error during login: {e}")
            exit(-6)

        # 3. Send email
        try:
            server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, message.as_string())
            print("Email alert sent successfully.")
        except smtplib.SMTPRecipientsRefused as e:
            # This often indicates invalid recipient email addresses
            print(f"SMTP Error: Server refused to send to one or more recipients: {e}. Check recipient email addresses.")
            exit(-7)
        except smtplib.SMTPSenderRefused as e:
            # This often indicates an invalid sender email address
            print(f"SMTP Error: Server refused sender email address: {e}. Check your sender email.")
            exit(-8)
        except smtplib.SMTPDataError as e:
            # This can indicate issues with the message content (e.g., too large, malformed)
            print(f"SMTP Data Error: Server refused to accept the message data: {e}. Check email content/size.")
            exit(-9)
        except smtplib.SMTPException as e:
            print(f"Generic SMTP Error during sending email: {e}")
            exit(-10)

except smtplib.SMTPConnectError as e:
    print(f"SMTP Connection Error: Could not connect to the SMTP server at {SMTP_SERVER}:{SMTP_PORT}. "
          f"Check server address, port, and network connectivity. Error: {e}")
except smtplib.SMTPNotSupportedError as e:
    print(f"SMTP Protocol Error: Server does not support the requested command (e.g., STARTTLS): {e}.")
except smtplib.SMTPException as e:
    # Catch any other smtplib specific errors not covered above
    print(f"An unexpected SMTP error occurred: {e}. This might be a generic server issue.")
except Exception as e:
    # Catch any other non-smtplib related exceptions (e.g., network issues not caught by smtplib)
    print(f"An unexpected error occurred while trying to send email: {e}")