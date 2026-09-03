# -*- coding: utf8 -*-

from string import Template

from utils.mail import send
from utils.token import generate_confirmation_token
from variables import API_URL, DATA_PATH, DISCORD_URL


def send_confirmation_email(mail):
    """ Generate a fresh confirmation token for `mail` and email the
    confirmation link. Always generates/stores the token regardless of
    whether the email actually goes out; returns whatever utils.mail.send()
    returns (True/False) so the caller can report mail delivery separately
    from account/token creation. Shared by register.py and resend.py. """
    subject = '[🐒&🐖] Bienvenue chez le Singouins !'
    token = generate_confirmation_token(mail)
    url = f'{API_URL}/confirm/{token}'
    with open(f"{DATA_PATH}/registered.html", "r") as f:
        email_body = f.read()

    # string.Template ($name), not str.format() ({name}) - the template is
    # mostly CSS, which is made of literal { }, so .format() would break
    # (or silently mangle output) the moment a <style> block gets added.
    email_body = Template(email_body).substitute(
        urllogo='[INSERT LOGO HERE]',
        urlconfirm=url,
        urldiscord=DISCORD_URL,
        )

    return send(mail, subject, email_body)
