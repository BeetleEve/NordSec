from django import template
from django.urls import reverse, NoReverseMatch
register = template.Library()


@register.filter
def ru_plural(value, forms):
    variants = forms.split(',')
    if len(variants) != 3:
        return ''
    number = abs(int(value))
    if 11 <= number % 100 <= 14:
        return variants[2]
    if number % 10 == 1:
        return variants[0]
    return variants[1] if 2 <= number % 10 <= 4 else variants[2]


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
