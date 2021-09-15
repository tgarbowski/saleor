import logging
import webbrowser

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import pytz
import requests
from django.core.mail import EmailMultiAlternatives
from django.shortcuts import redirect

from saleor.plugins.base_plugin import BasePlugin, ConfigurationTypeField
from saleor.plugins.manager import get_plugins_manager
from saleor.plugins.models import PluginConfiguration
from saleor.product.models import ProductImage
from . import ProductPublishState

logger = logging.getLogger(__name__)

from .tasks import async_product_publish
from .api import AllegroAPI

@dataclass
class AllegroConfiguration:
    redirect_url: str
    callback_url: str
    token_value: str
    client_id: str
    client_secret: str
    refresh_token: str
    saleor_redirect_url: str
    token_access: str
    auth_env: str
    env: str
    implied_warranty: str
    return_policy: str
    warranty: str
    delivery_shipping_rates: str
    delivery_handling_time: str
    publication_duration: str
    publication_starting_at: str
    auction_format: str
    interval_for_offer_publication: str
    offer_publication_chunks: str
    offer_description_footer: str


class AllegroPlugin(BasePlugin):
    PLUGIN_ID = "allegro"
    PLUGIN_NAME = "Allegro"
    PLUGIN_NAME_2 = "Allegro"
    META_CODE_KEY = "AllegroPlugin.code"
    META_DESCRIPTION_KEY = "AllegroPlugin.description"
    DEFAULT_CONFIGURATION = [{"name": "redirect_url",
                              "value": "https://allegro.pl.allegrosandbox.pl/auth/oauth"},
                             {"name": "callback_url",
                              "value": "http://localhost:8000/allegro"},
                             {"name": "saleor_redirect_url",
                              "value": "http://localhost:9000"},
                             {"name": "token_value", "value": None},
                             {"name": "client_id", "value": None},
                             {"name": "client_secret", "value": None},
                             {"name": "refresh_token", "value": None},
                             {"name": "token_access", "value": None},
                             {"name": "auth_env",
                              "value": "https://allegro.pl.allegrosandbox.pl"},
                             {"name": "env",
                              "value": "https://api.allegro.pl.allegrosandbox.pl"},
                             {"name": "implied_warranty", "value": None},
                             {"name": "return_policy", "value": None},
                             {"name": "warranty", "value": None},
                             {"name": "delivery_shipping_rates", "value": None},
                             {"name": "delivery_handling_time", "value": None},
                             {"name": "publication_duration", "value": None},
                             {"name": "publication_starting_at", "value": ''},
                             {"name": "auction_format", "value": 'AUCTION'},
                             {"name": "interval_for_offer_publication", "value": '5'},
                             {"name": "offer_publication_chunks", "value": '13'},
                             {"name": "offer_description_footer", "value": ''}, ]
    CONFIG_STRUCTURE = {
        "redirect_url": {
            "type": ConfigurationTypeField.STRING,
            "label": "Redirect URL np: https://allegro.pl.allegrosandbox.pl/auth/oauth",
        },
        "callback_url": {
            "type": ConfigurationTypeField.STRING,
            "label": "Callback URL:",
            "help_text": "Callback URL ustalany przy tworzeniu aplikacji po stronie allegro.",
        },
        "saleor_redirect_url": {
            "type": ConfigurationTypeField.STRING,
            "label": "Redirect URL saleora po autoryzacji:",
            "help_text": "URL saleora na ktory przekierowac po autoryzacji.",
        },
        "token_value": {
            "type": ConfigurationTypeField.SECRET,
            "help_text": "Wartośc tokena:",
            "label": "Wartość tokena.",
        },
        "client_id": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "ID klienta allegro generowany przez allegro.",
            "label": "ID klienta allegro:",
        },
        "client_secret": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Wartość skeretnego klucza generowanego przez allegro.",
            "label": "Wartość sekretnego klucza:",
        },
        "refresh_token": {
            "type": ConfigurationTypeField.SECRET,
            "help_text": "Wartośc refresh tokena.",
            "label": "Refresh token.",
        },
        "token_access": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Data uzupełni się automatycznie.",
            "label": "Data ważności tokena:",
        },
        "auth_env": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Adres do środowiska allegro.pl.",
            "label": "Adres do środowiska allegro.pl:",
        },
        "env": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Adres do środowiska api.allegro.pl.",
            "label": "Adres do środowiska api.allegro.pl:",
        },
        "implied_warranty": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "implied_warranty",
            "label": "implied_warranty",
        },
        "return_policy": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "return_policy",
            "label": "return_policy",
        },
        "warranty": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "warranty",
            "label": "warranty",
        },
        "delivery_shipping_rates": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "delivery_shipping_rates",
            "label": "delivery_shipping_rates",
        },
        "delivery_handling_time": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "delivery_handling_time (PT72H)",
            "label": "delivery_handling_time",
        },
        "publication_duration": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "publication_duration (PT72H)",
            "label": "publication_duration",
        },
        "publication_starting_at": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "publication_starting_at w formacie %Y-%m-%d %H:%M (2020-09-02 20:00)",
            "label": "publication_starting_at",
        },
        "auction_format": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "AUCTION lub BUY_NOW",
            "label": "auction_format",
        },
        "interval_for_offer_publication": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Podaj liczbe minut co ile mają być publikowane oferty.",
            "label": "interval_for_offer_publication",
        },
        "offer_publication_chunks": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Podaj liczbe przedziałow w ktorych mają być publikowane oferty.",
            "label": "offer_publication_chunks",
        },
        "offer_description_footer": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Podaj tekst który będzie widoczny na dole opisu oferty.",
            "label": "offer_description_footer",
        }
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        configuration = {item["name"]: item["value"] for item in self.configuration}

        self.config = AllegroConfiguration(redirect_url=configuration["redirect_url"],
                                           callback_url=configuration["callback_url"],
                                           saleor_redirect_url=configuration[
                                               "saleor_redirect_url"],
                                           token_access=configuration["token_access"],
                                           token_value=configuration["token_value"],
                                           client_id=configuration["client_id"],
                                           client_secret=configuration["client_secret"],
                                           refresh_token=configuration["refresh_token"],
                                           auth_env=configuration["auth_env"],
                                           env=configuration["env"],
                                           implied_warranty=configuration[
                                               "implied_warranty"],
                                           return_policy=configuration["return_policy"],
                                           warranty=configuration["warranty"],
                                           delivery_shipping_rates=configuration[
                                               "delivery_shipping_rates"],
                                           delivery_handling_time=configuration[
                                               "delivery_handling_time"],
                                           publication_duration=configuration[
                                               "publication_duration"],
                                           publication_starting_at=configuration[
                                               "publication_starting_at"],
                                           auction_format=configuration[
                                               "auction_format"],
                                           interval_for_offer_publication=configuration[
                                               "interval_for_offer_publication"],
                                           offer_publication_chunks=configuration[
                                               "offer_publication_chunks"],
                                           offer_description_footer=configuration[
                                               "offer_description_footer"])


    @classmethod
    def validate_plugin_configuration(cls, plugin_configuration: "PluginConfiguration"):
        """Validate if provided configuration is correct."""
        configuration = plugin_configuration.configuration
        configuration = {item["name"]: item["value"] for item in configuration}

        access_key = configuration.get("Access key")

    @classmethod
    def save_plugin_configuration(cls, plugin_configuration: "PluginConfiguration",
                                  cleaned_data):

        current_config = plugin_configuration.configuration

        configuration_to_update = cleaned_data.get("configuration")

        if configuration_to_update:
            cls._update_config_items(configuration_to_update, current_config)
        if "active" in cleaned_data:
            plugin_configuration.active = cleaned_data["active"]
        cls.validate_plugin_configuration(plugin_configuration)
        plugin_configuration.save()
        if plugin_configuration.configuration:
            # Let's add a translated descriptions and labels
            cls._append_config_structure(plugin_configuration.configuration)

        configuration = {item["name"]: item["value"] for item in
                         plugin_configuration.configuration}

        if (plugin_configuration.active == True and not configuration[
            'token_value'] and bool(configuration['client_id']) and bool(
            configuration['client_secret'])):
            allegro_auth = AllegroAuth()
            allegro_auth.get_access_code(configuration['client_id'],
                                         configuration['client_secret'],
                                         configuration['callback_url'],
                                         configuration['redirect_url'])

        return plugin_configuration

    def product_validate(self, product):
        errors = []

        product_variant = product.variants.first()

        if not self.active:
            errors.append('003: plugin jest nieaktywny')
        if product_variant.metadata.get('reserved') is True:
            errors.append('003: produkt jest zarezerwowany')
        if product_variant.stocks.first().quantity < 1:
            errors.append('002: stan magazynowy produktu wynosi 0')
        if product_variant.private_metadata.get('location') is None:
            errors.append('003: brak lokacji magazynowej dla produktu')
        '''
        if product_variant.price_amount == 0:
            errors.append('003: cena produktu wynosi 0')
        if product_variant.cost_price_amount == 0 \
                or product_variant.cost_price_amount is None:
            errors.append('003: cena zakupowa produktu wynosi 0')
        '''
        AllegroAPI(None, None).update_errors_in_private_metadata(product, errors)
        return errors

    def product_published(self, product_with_params: Any) -> Any:
        product = product_with_params.get('product')
        product_images = ProductMedia.objects.filter(product=product)
        product_images = [product_image.image.url for product_image in product_images]
        products_bulk_ids = product_with_params.get('products_bulk_ids')

        product.delete_value_from_private_metadata('publish.allegro.errors')
        product.is_published = True
        product.save()

        if len(self.product_validate(product)) == 0:
            async_product_publish(product_id=product.id,
                                        offer_type=product_with_params.get('offer_type'),
                                        starting_at=product_with_params.get('starting_at'),
                                        product_images=product_images,
                                        products_bulk_ids=products_bulk_ids)

        else:
            product.store_value_in_private_metadata(
                {'publish.allegro.status': ProductPublishState.MODERATED.value})
            product.store_value_in_private_metadata(
                {'publish.status.date': datetime.now(pytz.timezone('Europe/Warsaw'))
                    .strftime('%Y-%m-%d %H:%M:%S')})
            product.save(update_fields=["private_metadata"])

    def calculate_hours_to_token_expire(self):
        token_expire = datetime.strptime(self.config.token_access, '%d/%m/%Y %H:%M:%S')
        duration = token_expire - datetime.now()
        return divmod(duration.total_seconds(), 3600)[0]

    def get_intervals_and_chunks(self, previous_value: Any):
        return [int(self.config.interval_for_offer_publication),
                int(self.config.offer_publication_chunks)]

    def send_mail_with_publish_errors(self, publish_errors: Any,
                                      previous_value: Any) -> Any:
        if publish_errors is not None:
            return self.send_mail(publish_errors)

    @staticmethod
    def create_table(errors):
        html = '<table style="width:100%; margin-bottom: 1rem;">'
        html += '<tr>'
        html += '<th></th>'
        html += '</tr>'
        for error in errors:
            html += '<tr>'
            try:
                if len(error.get('errors')) > 0:
                    html += '<td style="width: 9rem;">' + str(error.get('sku')) + '</td>'
                    html += '<td>' + str(error.get('errors')) + '</td>'
            except:
                if len(error) > 0:
                    html += '<td>' + str(error) + '</td>'
            html += '</tr>'
        html += '<tr>'
        html += '<td>' + '</td>'
        html += '</tr>'
        html += '</table>'
        html += '<br>'
        html += '<table style="width:100%; margin-bottom: 1rem;">'
        html += '<tr>'
        #html += '<td>' + 'Poprawnie przetworzone: ' + str(len([error for error in errors if len(error.get('errors')) == 0])) + '</td>'
        html += '</tr>'
        html += '<tr>'
        #html += '<td>' + 'Niepropawnie przetworzone: ' + str(len([error for error in errors if len(error.get('errors')) > 0])) + '</td>'
        html += '</tr>'
        html += '</table>'

        return html

    def send_mail(self, errors):
        subject = 'Logi z wystawiania ofert'
        from_email = 'noreply.salingo@gmail.com'
        to = 'noreply.salingo@gmail.com'
        text_content = 'Logi z wystawiania ofert:'
        html_content = self.create_table(errors)
        message = EmailMultiAlternatives(subject, text_content, from_email, [to])
        message.attach_alternative(html_content, "text/html")
        return message.send()


class AllegroAuth:

    @staticmethod
    def get_access_code(client_id, api_key, redirect_uri,
                        oauth_url):
        # zmienna auth_url zawierać będzie zbudowany na podstawie podanych parametrów URL do zdobycia kodu
        auth_url = '{}/authorize' \
                   '?response_type=code' \
                   '&client_id={}' \
                   '&api-key={}' \
                   '&redirect_uri={}&prompt=confirm'.format(oauth_url, client_id,
                                                            api_key,
                                                            redirect_uri)

        webbrowser.open(auth_url)

        return True

    def sign_in(self, client_id, client_secret, access_code, redirect_uri, oauth_url):
        token_url = oauth_url + '/token'

        access_token_data = {'grant_type': 'authorization_code',
                             'code': access_code,
                             'redirect_uri': redirect_uri}

        response = requests.post(url=token_url,
                                 auth=requests.auth.HTTPBasicAuth(client_id,
                                                                  client_secret),
                                 data=access_token_data)

        access_token = response.json()['access_token']
        refresh_token = response.json()['refresh_token']
        expires_in = response.json()['expires_in']

        self.save_token_in_plugin_configuration(access_token, refresh_token, expires_in)

        return response.json()

    @staticmethod
    def save_token_in_plugin_configuration(access_token, refresh_token, expires_in):
        cleaned_data = {
            "configuration": [{"name": "token_value", "value": access_token},
                              {"name": "token_access",
                               "value": (datetime.now() + timedelta(
                                   seconds=expires_in)).strftime("%d/%m/%Y %H:%M:%S")},
                              {"name": "refresh_token", "value": refresh_token}]
        }

        AllegroPlugin.save_plugin_configuration(
            plugin_configuration=PluginConfiguration.objects.get(
                identifier=AllegroPlugin.PLUGIN_ID, channel_id=3), cleaned_data=cleaned_data, )

    def resolve_auth(request):
        manager = get_plugins_manager()
        plugin = manager.get_plugin(AllegroPlugin.PLUGIN_ID)
        allegro_auth = AllegroAuth()

        access_code = request.GET["code"]

        client_id = plugin.config.client_id
        client_secret = plugin.config.client_secret
        callback_url = plugin.config.callback_url
        default_redirect_uri = plugin.config.redirect_url

        allegro_auth.sign_in(client_id, client_secret, access_code,
                             callback_url, default_redirect_uri)

        return redirect(plugin.config.saleor_redirect_url)
