from django.contrib import messages
from django.contrib.auth.decorators import permission_required
from django.contrib.sites.models import Site
from django.contrib.sites.shortcuts import get_current_site
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.utils.translation import pgettext_lazy

from .forms import AuthorizationKeyFormSet, SiteForm, SiteSettingForm
from ..views import staff_member_required
from ...site.models import AuthorizationKey, SiteSettings


@staff_member_required
@permission_required('site.edit_settings')
def index(request):
    site = get_current_site(request)
    settings = site.settings
    return redirect('dashboard:site-detail', pk=settings.pk)



@staff_member_required
@permission_required('site.edit_settings')
def site_settings_edit(request, pk=None):
    if pk:
        site_settings = get_object_or_404(SiteSettings, pk=pk)
        site = site_settings.site
    else:
        site_settings = SiteSettings()
        site = Site()
    site_settings_form = SiteSettingsForm(
        request.POST or None, instance=site_settings)
    site_form = SiteForm(request.POST or None, instance=site)

    if site_settings_form.is_valid() and site_form.is_valid():
        site = site_form.save()
        site_settings_form.instance.site = site
        site_settings = site_settings_form.save()
        messages.success(request, pgettext_lazy(
            'Dashboard message', 'Updated site %s') % site_settings)
        return redirect('dashboard:site-detail', pk=site_settings.id)
    ctx = {'site': site_settings, 'site_settings_form': site_settings_form,
           'site_form': site_form}
    return TemplateResponse(request, 'dashboard/sites/form.html', ctx)


@superuser_required
def site_settings_detail(request, pk):
    site_settings = get_object_or_404(SiteSettings, pk=pk)
    authorization_keys = AuthorizationKey.objects.filter(
        site_settings=site_settings)
    ctx = {'site': site_settings, 'authorization_keys': authorization_keys}
    return TemplateResponse(request, 'dashboard/sites/detail.html', ctx)


@superuser_required
def authorization_key_edit(request, site_settings_pk, key_pk=None):
    if key_pk:
        key = get_object_or_404(AuthorizationKey, pk=key_pk)
    else:
        key = AuthorizationKey(site_settings_id=site_settings_pk)
    form = AuthorizationKeyForm(request.POST or None, instance=key)
    if form.is_valid():
        key = form.save()
        msg = pgettext_lazy(
            'dashboard message',
            'Updated country shipping price %s') % (key,) \
            if key_pk else pgettext_lazy(
            'Dashboard message', 'Added country shipping price %s') % (key,)
        messages.success(request, msg)
        return redirect(
            'dashboard:site-detail', pk=site_settings_pk)
    ctx = {'form': form, 'site_settings_pk': site_settings_pk, 'key': key}
    return TemplateResponse(
        request, 'dashboard/sites/authorization_keys/form.html', ctx)


@superuser_required
def authorization_key_delete(request, site_settings_pk, key_pk):
    key = get_object_or_404(AuthorizationKey, pk=key_pk)
    if request.method == 'POST':
        key.delete()
        messages.success(
            request,
            pgettext_lazy(
                'Dashboard message',
                'Removed site authorization key %s') %
            (key,))
        return redirect(
            'dashboard:site-detail', pk=site_settings_pk)
    return TemplateResponse(
        request, 'dashboard/sites/modal/confirm_delete.html',
        {'key': key, 'site_settings_pk': site_settings_pk})
