from django import template
from django.urls import reverse, NoReverseMatch
register = template.Library()


@register.simple_tag(takes_context=True)
def querystring(context, **kwargs):
    params = context['request'].GET.copy()
    for key, value in kwargs.items():
        params[key] = value
    return params.urlencode()


@register.filter
def route_url(value):
    if not value:
        return reverse('dashboard')
    if str(value).startswith('/'):
        return value
    try:
        return reverse(value)
    except NoReverseMatch:
        return reverse('dashboard')
