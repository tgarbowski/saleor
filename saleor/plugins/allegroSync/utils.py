import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from django.conf import settings


def valid_product(product):
    errors = []
    # TODO pass is_published from ProductChannelListing
    '''
    if not product.is_published:
        errors.append('flaga is_published jest ustawiona na false')
    '''
    if product.private_metadata.get('publish.allegro.status') != 'published':
        errors.append('publish.allegro.status != published')

    return errors


def send_mail(html_errors_list, updated_amount):
    password = settings.EMAIL_HOST_PASSWORD
    server = smtplib.SMTP('smtp.gmail.com', 587)
    server.starttls()
    server.login('noreply.salingo@gmail.com', password)

    msg = MIMEMultipart('alternative')
    html = MIMEText(f'Uaktualniono {updated_amount} ofert.' + html_errors_list, 'html')
    msg.attach(html)
    msg['Subject'] = 'Logi z synchronizacji ofert'
    msg['From'] = 'sync+noreply.salingo@gmail.com'
    msg['To'] = 'sync+noreply.salingo@gmail.com'

    server.sendmail('noreply.salingo@gmail.com', 'noreply.salingo@gmail.com', msg.as_string())
