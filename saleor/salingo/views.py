import json

from django.http import HttpResponse
from django.views.decorators.http import require_POST

from saleor.salingo.tasks import publish_local_shop
from saleor.salingo.remover import bulk_sign_images_by_url
from saleor.salingo.utils import remover_auth


@require_POST
@remover_auth
def remover_notify(request):
    images = json.loads(request.body.decode('utf-8')).get('images')

    try:
        bulk_sign_images_by_url(media_urls=images)
        publish_local_shop(channel_slug='fashion4you')
    except:
        return HttpResponse(status=400)

    return HttpResponse(status=200)
