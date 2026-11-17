from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone
from .models import User


def clean_phone(value):
    value = value.strip()
    digits = ''.join(c for c in value if c.isdigit())
    if len(digits) < 10 or len(digits) > 15:
        raise forms.ValidationError('Введите телефон: от 10 до 15 цифр, например +7 900 123-45-67.')
    return value


class RegisterForm(UserCreationForm):
    first_name = forms.CharField(label='Имя', max_length=150)
    last_name = forms.CharField(label='Фамилия', max_length=150)
    phone = forms.CharField(label='Телефон', max_length=30)
    email = forms.EmailField(label='Электронная почта', required=False)
    consent = forms.BooleanField(label='Я ознакомился с условиями обработки персональных данных')

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'username', 'phone', 'email', 'district', 'password1', 'password2', 'consent']
        labels = {'username': 'Логин'}

    def clean_phone(self):
        return clean_phone(self.cleaned_data['phone'])

    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = User.Role.MEMBER
        user.consent_at = timezone.now()
        if commit:
            user.save()
        return user


class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'phone', 'email', 'district']

    def clean_phone(self):
        return clean_phone(self.cleaned_data['phone'])
