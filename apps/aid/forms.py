from datetime import timedelta
from io import BytesIO
from django import forms
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.utils import timezone
from PIL import Image, ImageOps, UnidentifiedImageError
from apps.accounts.forms import clean_phone
from .models import Item, HelpRequest, Reservation, VolunteerTask, VolunteerApplication
from .districts import district_at


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


class ContactFormMixin:
    contact_phone = forms.CharField(label='Телефон для связи', max_length=30)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            for name in ('donor_name', 'recipient_name', 'contact_phone', 'category'):
                if name in self.fields:
                    value = getattr(self.instance, name)
                    self.initial[name] = value.pk if hasattr(value, 'pk') else value

    def save(self, commit=True):
        obj = super().save(commit=False)
        for name in ('donor_name', 'recipient_name', 'contact_phone', 'category'):
            if name in self.cleaned_data:
                setattr(obj, name, self.cleaned_data[name])
        if commit:
            obj.save()
        return obj


class ItemForm(ContactFormMixin, PhotoMixin, forms.ModelForm):
    donor_name = forms.CharField(label='Как к вам обращаться', max_length=150, required=False)
    contact_phone = forms.CharField(label='Телефон для связи', max_length=30, required=False, help_text='Для вещи у владельца телефон увидят вошедшие участники. Для отметки на улице он не нужен.')
    def __init__(self, *args, **kwargs):
        # Older clients had only owner listings; preserve their explicit address workflow.
        if args and args[0] is not None and 'placement' not in args[0]:
            data = args[0].copy()
            data['placement'] = Item.Placement.HOME
            args = (data, *args[1:])
        if kwargs.get('data') is not None and 'placement' not in kwargs['data']:
            kwargs['data'] = kwargs['data'].copy()
            kwargs['data']['placement'] = Item.Placement.HOME
        data = args[0] if args and args[0] is not None else kwargs.get('data')
        if data is not None and not data.get('district'):
            try:
                detected = district_at(data.get('latitude') or None, data.get('longitude') or None)
            except (ValueError, TypeError, OverflowError):
                detected = None
            if detected:
                data = data.copy()
                data['district'] = detected
                if args:
                    args = (data, *args[1:])
                else:
                    kwargs['data'] = data
        super().__init__(*args, **kwargs)
        if self.data.get('placement', self.initial.get('placement')) == Item.Placement.STREET:
            for name in ('donor_name', 'contact_phone'):
                self.fields[name].disabled = True
                self.initial[name] = ''

    class Meta:
        model = Item
        fields = ['placement', 'category', 'title', 'condition', 'description', 'pickup_address', 'latitude', 'longitude', 'location_accuracy', 'photo', 'size', 'district', 'donor_name', 'contact_phone']
        widgets = {'description': forms.Textarea(attrs={'rows': 5}), 'photo': forms.ClearableFileInput(attrs={'accept': 'image/jpeg,image/png,image/webp', 'capture': 'environment'}), 'latitude': forms.HiddenInput(), 'longitude': forms.HiddenInput(), 'location_accuracy': forms.HiddenInput()}
        help_texts = {
            'condition': 'Если не проверяли вещь, выберите «Не проверено». Можно размещать вещи на запчасти.',
            'pickup_address': 'Введите адрес или выберите точку на карте.',
            'district': 'Определяется по точке на карте. Проверьте выбранный район.',
            'photo': 'JPG, PNG или WEBP до 5 МБ. Не добавляйте документы и личные данные.',
            'needs_transport': 'Доставка определяется отдельно и зависит от доступности волонтёров.',
        }

    def clean_condition(self):
        return self.cleaned_data.get('condition') or Item.Condition.UNKNOWN

    def clean_contact_phone(self):
        value = self.cleaned_data.get('contact_phone', '')
        return clean_phone(value) if value else ''


    def clean(self):
        data = super().clean()
        lat, lon = data.get('latitude'), data.get('longitude')
        if (lat is None) != (lon is None):
            self.add_error('pickup_address', 'Выберите точку на карте заново.')
        if lat is not None and not -90 <= lat <= 90:
            self.add_error('pickup_address', 'Некорректная широта.')
        if lon is not None and not -180 <= lon <= 180:
            self.add_error('pickup_address', 'Некорректная долгота.')
        if not data.get('pickup_address') and lat is None:
            self.add_error('pickup_address', 'Укажите адрес или поставьте метку на карте.')
        if data.get('placement') == 'street':
            if (data.get('location_accuracy') or 0) > 100:
                self.add_error('pickup_address', 'Геолокация слишком неточная. Уточните точку вручную на карте.')
            if lat is None or lon is None:
                self.add_error('pickup_address', 'Для вещи на улице нужна метка на карте.')
            if not data.get('photo'):
                self.add_error('photo', 'Сфотографируйте вещь на месте, чтобы её можно было узнать.')
            if self.instance.pk and not self.files.get('photo') and (self.initial.get('placement') != 'street' or (self.instance.expires_at and self.instance.expires_at <= timezone.now())):
                self.add_error('photo', 'Для новой отметки на улице сделайте актуальное фото на месте.')
            data['donor_name'] = ''
            data['contact_phone'] = ''
        elif not data.get('contact_phone'):
            self.add_error('contact_phone', 'Укажите телефон для прямой связи с получателем.')
        return data


class HelpRequestForm(ContactFormMixin, forms.ModelForm):
    recipient_name = forms.CharField(label='Имя получателя', max_length=150)
    contact_phone = forms.CharField(label='Телефон для связи', max_length=30)
    category = forms.ModelChoiceField(label='Категория', queryset=Item._meta.get_field('category').remote_field.model.objects.all())
    consent = forms.BooleanField(label='Разрешаю обработку данных обращения')

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
            self.add_error('delivery_address', 'Для обсуждения доставки укажите адрес.')
        return data


class RequestEditForm(ContactFormMixin, forms.ModelForm):
    recipient_name = forms.CharField(label='Имя получателя', max_length=150)
    contact_phone = forms.CharField(label='Телефон для связи', max_length=30)
    class Meta:
        model = HelpRequest
        fields = ['need', 'recipient_name', 'contact_phone', 'district', 'needs_delivery', 'delivery_address']
        labels = {'need': 'Комментарий к заявке'}
        widgets = {'need': forms.Textarea(attrs={'rows': 5})}

    def clean_contact_phone(self):
        return clean_phone(self.cleaned_data['contact_phone'])

    def clean(self):
        data = super().clean()
        if data.get('needs_delivery') and not data.get('delivery_address'):
            self.add_error('delivery_address', 'Для обсуждения доставки укажите адрес.')
        return data


class ClarificationForm(ContactFormMixin, forms.ModelForm):
    contact_phone = forms.CharField(label='Телефон для связи', max_length=30)
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
    action = forms.ChoiceField(label='Решение', choices=[('approve', 'Разрешить публикацию'), ('reject', 'Отклонить объявление')])
    reason = forms.CharField(label='Комментарий автору', max_length=1500, required=False, widget=forms.Textarea(attrs={'rows': 3}))

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
            self.fields['item'].queryset = self.fields['item'].queryset.filter(pk=help_request.preferred_item_id)
            self.fields['item'].initial = help_request.preferred_item_id


class ReasonForm(forms.Form):
    reason = forms.CharField(label='Причина', max_length=1500, widget=forms.Textarea(attrs={'rows': 4}))


class ReservationCancelForm(ReasonForm):
    return_location = forms.ChoiceField(label='Возврат вещи (только после фактической проверки)', required=False, choices=[('', 'Вещь не перемещалась'), ('donor', 'Возврат жертвователю подтверждён'), ('fund', 'Возврат в пункт фонда подтверждён')])


class TransferForm(forms.Form):
    transferred_at = forms.DateTimeField(label='Фактические дата и время передачи', widget=forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'), initial=timezone.localtime)
    note = forms.CharField(label='Как подтверждено получение', max_length=1500, widget=forms.Textarea(attrs={'rows': 4}), help_text='Например: получатель лично подтвердил выдачу координатору по телефону.')
    confirmed = forms.BooleanField(label='Подтверждаю, что вещь фактически получена, а не только отмечена к передаче')


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
        widgets = {'description': forms.Textarea(attrs={'rows': 4}), 'availability': forms.TextInput(attrs={'placeholder': 'Например, по выходным после 12:00'})}
        labels = {'availability': 'В какое время можете помогать'}
        help_texts = {'availability': 'Напишите дни недели и время в свободной форме. Можно оставить пустым.'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['availability'].required = False


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
