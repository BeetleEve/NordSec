from functools import wraps
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.utils import timezone
from .models import Item, HelpRequest, VolunteerTask


def coordinator_required(view):
    @login_required
    @wraps(view)
    def guarded(request, *args, **kwargs):
        if not request.user.is_coordinator:
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return guarded


def visible_items(user):
    public = Q(status__in=[Item.Status.AVAILABLE, Item.Status.RESERVED]) & (Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
    if not user.is_authenticated:
        return Item.objects.filter(public)
    if user.is_coordinator:
        return Item.objects.all()
    related = Q(donor=user) | Q(reservations__request__recipient=user) | Q(reservations__task__volunteer=user)
    return Item.objects.filter(public | related).distinct()


def visible_requests(user):
    if user.is_coordinator:
        return HelpRequest.objects.all()
    return HelpRequest.objects.filter(recipient=user)


def visible_tasks(user):
    if user.is_coordinator:
        return VolunteerTask.objects.all()
    if user.is_volunteer:
        return VolunteerTask.objects.filter(Q(status=VolunteerTask.Status.OPEN) | Q(volunteer=user))
    return VolunteerTask.objects.none()


def public_items():
    return Item.objects.filter(status=Item.Status.AVAILABLE).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()))
