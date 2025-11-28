import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

# ----------------------------------------------------------------------
# Configuration pulled directly from config.toml
# ----------------------------------------------------------------------
SMTP_SERVER = "bezaman.parkcircus.org"
SMTP_PORT = 587
SMTP_USERNAME = "iot_admi"
SMTP_PASSWORD = "Apna2Chabee!"
SENDER_EMAIL = "chowkidar@parkcircus.org"
RECIPIENT_EMAIL = "reza@parkcircus.org"

# ----------------------------------------------------------------------
# Email Content
# ----------------------------------------------------------------------
CURRENT_TIME = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
SUBJECT = f"SMTP Connectivity Test - {CURRENT_TIME}"
BODY = (
    "This is an automated test email to debug connectivity issues.\n"
    f"Test initiated at: {CURRENT_TIME}\n"
    "If you receive this, the connection, authentication, and mail transaction were successful."
)


def run_smtp_test():
    """Attempts a full SMTP transaction with granular error handling."""
    print("=====================================================================")
    print("Starting SMTP Connectivity Test...")
    print(f"Target Server: {SMTP_SERVER}:{SMTP_PORT}")
    print(f"User: {SMTP_USERNAME}")
    print(f"Recipient: {RECIPIENT_EMAIL}")
    print("=====================================================================")

    # 1. Create the MIME message
    msg = MIMEMultipart()
    msg['From'] = SENDER_EMAIL
    msg['To'] = RECIPIENT_EMAIL
    msg['Subject'] = SUBJECT
    msg.attach(MIMEText(BODY, 'plain'))

    # Use default SSL context for secure connection
    context = ssl.create_default_context()
    server = None  # Initialize server variable outside the try block

    try:
        # 2. Connect to the SMTP server
        print(f"\n[STEP 1/5] Attempting connection to {SMTP_SERVER}:{SMTP_PORT}...")
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        print("[SUCCESS] Connection established.")

        # 3. Perform initial handshake
        print("[STEP 2/5] Performing initial EHLO handshake...")
        server.ehlo()
        print("[SUCCESS] EHLO handshake complete.")

        # 4. Start TLS encryption
        print("[STEP 3/5] Starting TLS encryption...")
        server.starttls(context=context)

        # NOTE: Second EHLO after STARTTLS is best practice
        server.ehlo()
        print("[SUCCESS] TLS established.")

        # 5. Log in
        print(f"[STEP 4/5] Attempting login with username '{SMTP_USERNAME}'...")
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        print("[SUCCESS] Authentication successful.")

        # 6. Send the email
        print(f"[STEP 5/5] Sending mail from '{SENDER_EMAIL}' to '{RECIPIENT_EMAIL}'...")
        server.sendmail(SENDER_EMAIL, RECIPIENT_EMAIL, msg.as_string())
        print("---------------------------------------------------------------------")
        print("✅ SUCCESS: Mail transaction reported as successful by the server.")
        print("If email is not received, the issue is server-side (e.g., policy, spam filter, routing).")
        print("---------------------------------------------------------------------")

    except smtplib.SMTPAuthenticationError:
        print("---------------------------------------------------------------------")
        print("❌ ERROR: SMTP Authentication Failed.")
        print("ACTION: Check 'smtp_username' and 'smtp_password' in config.toml.")
        print("---------------------------------------------------------------------")

    except smtplib.SMTPConnectError as e:
        print("---------------------------------------------------------------------")
        print("❌ ERROR: SMTP Connection Failed.")
        print(f"REASON: Could not connect to {SMTP_SERVER}:{SMTP_PORT}.")
        print("ACTION: Check network connection, server address/port, and firewall rules.")
        print(f"Detailed Error: {e}")
        print("---------------------------------------------------------------------")

    except smtplib.SMTPException as e:
        # This is the crucial block for catching protocol errors (5xx, 4xx responses)
        # after successful connection/login but before/during mail sending commands (MAIL FROM/RCPT TO)
        print("---------------------------------------------------------------------")
        print("❌ ERROR: SMTP Protocol Failure (Server Rejected Mail Transaction).")
        print("This means the server accepted connection/login but rejected the email commands.")
        print(
            "ACTION: The error code below points to the specific rejection cause (e.g., relaying denied, sender/recipient rejected).")
        print(f"Detailed Error: {e}")
        print("---------------------------------------------------------------------")

    except Exception as e:
        # Catch-all for TLS/SSL errors, timeouts, and other unexpected errors
        print("---------------------------------------------------------------------")
        print("❌ ERROR: Unexpected Error During SMTP Test.")
        print(f"Detailed Error: {e}")
        print("---------------------------------------------------------------------")

    finally:
        if server:
            try:
                server.quit()
            except Exception:
                pass  # Ignore errors during quit


if __name__ == "__main__":
    run_smtp_test()