from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect, render
from .forms import RegisterForm, ProfileForm


def register(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        with transaction.atomic():
            user = form.save()
        login(request, user)
        messages.success(request, 'Аккаунт создан. Теперь можно предложить вещи или оставить обращение.')
        return redirect('dashboard')
    return render(request, 'accounts/register.html', {'form': form})


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, instance=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Контактные данные обновлены.')
        return redirect('profile')
    return render(request, 'accounts/profile.html', {'form': form})
