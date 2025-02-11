from prefect import flow
from prefect_email import EmailServerCredentials, email_send_message
from jinja2 import Environment, FileSystemLoader, select_autoescape

jinja_env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape()
)

@flow
def send_run_summary_email(run_data, email_addresses):
    email_template = jinja_env.get_template("email_template.j2")
    email_text = email_template.render(run_data=run_data)

    email_server_credentials = EmailServerCredentials.load("paige-mediacloud-email-password")
    
    for email_address in email_addresses:
        subject = email_send_message.with_options(name=f"email {email_address}").submit(
            email_server_credentials=email_server_credentials,
            subject="Sous-Chef Execution Summary",
            msg=email_text,
            email_to=email_address,
        )