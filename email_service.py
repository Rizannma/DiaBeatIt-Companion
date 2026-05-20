"""Email service using Brevo (formerly Sendinblue)"""
import sib_api_v3_sdk
from sib_api_v3_sdk import Configuration, ApiClient, TransactionalEmailsApi
from sib_api_v3_sdk.rest import ApiException
from config import Config


def configure_brevo():
    """Configure Brevo API client"""
    configuration = Configuration()
    configuration.api_key['api-key'] = Config.BREVO_API_KEY
    return ApiClient(configuration)


def send_otp_email(email, otp, subject="Your OTP Code"):
    """Send OTP email to user"""
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{subject}</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                background-color: #f8f9fa;
                margin: 0;
                padding: 0;
            }}
            .container {{
                max-width: 600px;
                margin: 0 auto;
                background-color: #ffffff;
                padding: 20px;
                border-radius: 8px;
                box-shadow: 0 0 10px rgba(0,0,0,0.1);
            }}
            .header {{
                text-align: center;
                padding: 20px 0;
            }}
            .logo {{
                font-size: 24px;
                font-weight: bold;
                color: #0a0a0b;
            }}
            .content {{
                padding: 20px;
                text-align: center;
            }}
            .otp-code {{
                font-size: 32px;
                font-weight: bold;
                color: #dc3545;
                margin: 20px 0;
                letter-spacing: 5px;
            }}
            .footer {{
                text-align: center;
                padding: 20px;
                font-size: 12px;
                color: #6c757d;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <div class="logo">DiaBeatIt</div>
                <p>Your AI Diabetes Companion</p>
            </div>
            <div class="content">
                <h2>{subject}</h2>
                <p>Your OTP code is:</p>
                <div class="otp-code">{otp}</div>
                <p>Please enter this code to proceed.</p>
            </div>
            <div class="footer">
                <p>If you didn't request this, please ignore this email.</p>
            </div>
        </div>
    </body>
    </html>
    """
    
    api_client = configure_brevo()
    api_instance = TransactionalEmailsApi(api_client)
    
    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        to=[{"email": email}],
        sender={"email": Config.SENDER_EMAIL, "name": Config.SENDER_NAME},
        subject=subject,
        html_content=html_content
    )
    
    try:
        api_response = api_instance.send_transac_email(send_smtp_email)
        print(f"Email sent: {api_response}")
        return True
    except ApiException as e:
        print(f"Exception when calling SMTPApi->send_transac_email: {e}")
        return False


def send_report_email(email, subject, html_content):
    """Send report email to doctor or caregiver."""
    api_client = configure_brevo()
    api_instance = TransactionalEmailsApi(api_client)

    send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
        to=[{"email": email}],
        sender={"email": Config.SENDER_EMAIL, "name": Config.SENDER_NAME},
        subject=subject,
        html_content=html_content
    )

    try:
        api_response = api_instance.send_transac_email(send_smtp_email)
        print(f"Report email sent: {api_response}")
        return True
    except ApiException as e:
        print(f"Exception when sending report email: {e}")
        return False
