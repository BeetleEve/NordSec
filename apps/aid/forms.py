from datetime import timedelta
from io import BytesIO
from django import forms
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError
from apps.accounts.forms import clean_phone
from .models import Item, HelpRequest, Reservation, VolunteerTask, VolunteerApplication


class PhotoMixin:
    def clean_photo(self):
        upload = self.cleaned_data.get('photo')
        if not upload or not hasattr(upload, 'content_type'):
            return upload
        if upload.size > 5 * 1024 * 1024:
            raise forms.ValidationError('Фото должно быть не больше 5 МБ.')
        try:
            image = Image.open(upload)
            if image.format not in ('JPEG', 'PNG', 'WEBP') or image.width * image.height > 24_000_000:
                raise ValueError
            image.load()
            image = ImageOps.exif_transpose(image).convert('RGB')
            image.thumbnail((1600, 1600))
            buffer = BytesIO()
            image.save(buffer, format='JPEG', quality=88)
            size = buffer.tell()
            buffer.seek(0)
            return InMemoryUploadedFile(buffer, 'photo', 'photo.jpg', 'image/jpeg', size, None)
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
            raise forms.ValidationError('Загрузите корректное фото JPG, PNG или WEBP. Максимум 24 мегапикселя.')


class ItemForm(PhotoMixin, forms.ModelForm):
    class Meta:
        model = Item
        fields = ['title', 'category', 'description', 'condition', 'size', 'district', 'pickup_address', 'needs_transport', 'photo', 'donor_name', 'contact_phone']
        widgets = {'description': forms.Textarea(attrs={'rows': 5}), 'photo': forms.ClearableFileInput(attrs={'accept': 'image/jpeg,image/png,image/webp'})}
        help_texts = {
            'pickup_address': 'Точный адрес увидят только координатор и назначенный волонтёр.',
            'photo': 'JPG, PNG или WEBP до 5 МБ. Не добавляйте документы и личные данные.',
            'needs_transport': 'Доставка согласуется отдельно и зависит от доступности волонтёров.',
        }

    def clean_contact_phone(self):
        return clean_phone(self.cleaned_data['contact_phone'])


class HelpRequestForm(forms.ModelForm):
    consent = forms.BooleanField(label='Согласен на обработку данных обращения для организации помощи')

    class Meta:
        model = HelpRequest
        fields = ['category', 'need', 'recipient_name', 'contact_phone', 'district', 'needs_delivery', 'delivery_address']
        widgets = {'need': forms.Textarea(attrs={'rows': 5})}
        help_texts = {'need': 'Опишите нужную вещь, размер и другие важные характеристики. Медицинские и паспортные данные не нужны.', 'delivery_address': 'Адрес не публикуется. Если доставка не нужна, можно оставить поле пустым.'}

    def clean_contact_phone(self):
        return clean_phone(self.cleaned_data['contact_phone'])

    def clean(self):
        data = super().clean()
        if data.get('needs_delivery') and not data.get('delivery_address'):
            self.add_error('delivery_address', 'Для согласования доставки укажите адрес.')
        return data


class ClarificationForm(forms.ModelForm):
    class Meta:
        model = HelpRequest
        fields = ['need', 'contact_phone', 'delivery_address']
        widgets = {'need': forms.Textarea(attrs={'rows': 5})}

    def clean_contact_phone(self):
        return clean_phone(self.cleaned_data['contact_phone'])


class DecisionForm(forms.Form):
    action = forms.ChoiceField(label='Решение', choices=[('approve', 'Одобрить'), ('clarify', 'Запросить уточнение'), ('reject', 'Отказать')])
    reason = forms.CharField(label='Сообщение получателю', required=False, max_length=1500, widget=forms.Textarea(attrs={'rows': 3}))
    staff_note = forms.CharField(label='Служебный комментарий', required=False, max_length=2000, widget=forms.Textarea(attrs={'rows': 3}))

    def clean(self):
        data = super().clean()
        if data.get('action') in ('clarify', 'reject') and not data.get('reason', '').strip():
            self.add_error('reason', 'Укажите причину или вопрос получателю.')
        return data


class ItemReviewForm(forms.Form):
    action = forms.ChoiceField(label='Решение', choices=[('approve', 'Принять вещь'), ('reject', 'Отклонить предложение')])
    location = forms.ChoiceField(label='Подтверждённое местонахождение', choices=[('donor', 'У жертвователя'), ('fund', 'В пункте фонда')])
    reason = forms.CharField(label='Комментарий жертвователю', max_length=1500, required=False, widget=forms.Textarea(attrs={'rows': 3}))

    def clean(self):
        data = super().clean()
        if data.get('action') == 'reject' and not data.get('reason', '').strip():
            self.add_error('reason', 'Укажите причину отклонения.')
        return data


class ReservationForm(forms.Form):
    item = forms.ModelChoiceField(label='Вещь', queryset=Item.objects.none())
    expires_at = forms.DateTimeField(label='Резерв до', widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'), initial=lambda: timezone.localtime() + timedelta(days=3))
    meeting_at = forms.DateTimeField(label='Время передачи', required=False, widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'))
    meeting_note = forms.CharField(label='Место и условия встречи', max_length=500, required=False, widget=forms.Textarea(attrs={'rows': 3}))

    def __init__(self, *args, help_request, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['item'].queryset = Item.objects.filter(status=Item.Status.AVAILABLE, category=help_request.category).exclude(donor_id=help_request.recipient_id) if help_request.recipient_id else Item.objects.filter(status=Item.Status.AVAILABLE, category=help_request.category)
        if help_request.preferred_item_id:
            self.fields['item'].initial = help_request.preferred_item_id


class ReasonForm(forms.Form):
    reason = forms.CharField(label='Причина', max_length=1500, widget=forms.Textarea(attrs={'rows': 4}))


class ReservationCancelForm(ReasonForm):
    return_location = forms.ChoiceField(label='Возврат вещи (только после фактической проверки)', required=False, choices=[('', 'Вещь не перемещалась'), ('donor', 'Возврат жертвователю подтверждён'), ('fund', 'Возврат в пункт фонда подтверждён')])


class TransferForm(forms.Form):
    transferred_at = forms.DateTimeField(label='Фактические дата и время передачи', widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'), initial=timezone.localtime)
    note = forms.CharField(label='Как подтверждено получение', max_length=1500, widget=forms.Textarea(attrs={'rows': 4}), help_text='Например: получатель лично подтвердил выдачу координатору по телефону.')
    confirmed = forms.BooleanField(label='Подтверждаю, что вещь фактически получена, а не только согласована к передаче')


class TransferReversalForm(ReasonForm):
    return_location = forms.ChoiceField(label='Подтверждённое местонахождение вещи', choices=[('donor', 'У жертвователя'), ('fund', 'В пункте фонда')])
    confirmed = forms.BooleanField(label='Проверено, что вещь действительно находится в указанном месте')


class TaskForm(forms.ModelForm):
    class Meta:
        model = VolunteerTask
        fields = ['title', 'description', 'pickup_address', 'dropoff_address', 'scheduled_at']
        widgets = {'description': forms.Textarea(attrs={'rows': 4}), 'scheduled_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M')}

    def clean_scheduled_at(self):
        value = self.cleaned_data['scheduled_at']
        if value <= timezone.now():
            raise forms.ValidationError('Укажите будущее время.')
        return value


class TaskActionForm(forms.Form):
    action = forms.ChoiceField(widget=forms.HiddenInput, choices=[('accept', 'Принять'), ('decline', 'Отказаться'), ('start', 'Забрал вещь'), ('deliver', 'Доставил')])
    note = forms.CharField(label='Комментарий', max_length=1500, required=False, widget=forms.Textarea(attrs={'rows': 3}))


class VolunteerForm(forms.ModelForm):
    class Meta:
        model = VolunteerApplication
        fields = ['availability', 'has_vehicle', 'description']
        widgets = {'description': forms.Textarea(attrs={'rows': 4})}


class VolunteerDecisionForm(ReasonForm):
    action = forms.ChoiceField(label='Решение', choices=[('approve', 'Принять в волонтёры'), ('reject', 'Отклонить')])
    reason = forms.CharField(label='Комментарий', max_length=1500, required=False, widget=forms.Textarea(attrs={'rows': 3}))


class ReportForm(forms.Form):
    start = forms.DateField(label='С', widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    end = forms.DateField(label='По', widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))

    def clean(self):
        data = super().clean()
        if data.get('start') and data.get('end'):
            if data['start'] > data['end']:
                raise forms.ValidationError('Дата начала должна быть не позднее даты окончания.')
            if (data['end'] - data['start']).days > 366:
                raise forms.ValidationError('Выберите период не больше года.')
        return data
