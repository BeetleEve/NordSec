from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from unittest.mock import patch, MagicMock
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from apps.aid import services
from apps.aid.forms import ItemForm
from apps.aid.models import Item, ItemSignal
from .base import AidCase


def photo():
    stream = BytesIO()
    Image.new('RGB', (40, 40), 'white').save(stream, format='JPEG')
    return SimpleUploadedFile('found.jpg', stream.getvalue(), content_type='image/jpeg')


class MapPlatformTests(AidCase):
    def setUp(self):
        self.street = self.make_item(title='Стул на улице', placement='street', latitude=Decimal('69.349785'), longitude=Decimal('88.201376'), pickup_address='У скамейки', expires_at=timezone.now()+timedelta(hours=6))
        self.home = self.make_item(title='Вещь у владельца', latitude=Decimal('69.349785'), longitude=Decimal('88.201376'))

    def test_public_map_shows_exact_street_and_rounded_owner_location(self):
        data = self.client.get(reverse('map_markers')).json()['items']
        street = next(x for x in data if x['id'] == self.street.pk)
        home = next(x for x in data if x['id'] == self.home.pk)
        self.assertEqual(street['latitude'], 69.349785)
        self.assertEqual(street['place'], 'У скамейки')
        self.assertEqual(home['latitude'], 69.350)
        self.assertEqual(home['longitude'], 88.201)
        self.assertTrue(home['approximate'])
        self.assertNotIn('НЕПУБЛИЧНЫЙ', str(home))
        self.assertNotIn('contact_phone', home)

    def test_bounds_queries_cannot_probe_exact_owner_position(self):
        bounds='88.201370,69.349780,88.201380,69.349790'
        ids = [x['id'] for x in self.client.get(reverse('map_markers'), {'bounds': bounds}).json()['items']]
        self.assertIn(self.street.pk, ids)
        self.assertNotIn(self.home.pk, ids)
        self.assertEqual(self.client.get(reverse('map_markers'), {'bounds': 'NaN,1,2,3'}).status_code, 400)

    def test_expired_or_review_listings_never_appear_on_map_or_public_catalog(self):
        self.street.expires_at=timezone.now()-timedelta(seconds=1)
        self.street.save()
        self.home.status=Item.Status.REVIEW
        self.home.save()
        self.assertEqual(self.client.get(reverse('map_markers')).json()['items'], [])
        self.assertNotContains(self.client.get(reverse('catalog')), self.street.title)
        self.assertEqual(self.client.get(self.street.get_absolute_url()).status_code, 404)

    def test_contact_is_login_only_and_street_never_shows_author_phone(self):
        self.assertEqual(self.client.get(reverse('item_contact', args=[self.home.pk])).status_code, 302)
        self.client.force_login(self.recipient)
        self.assertContains(self.client.get(reverse('item_contact', args=[self.home.pk])), self.home.contact_phone)
        self.assertRedirects(self.client.get(reverse('item_contact', args=[self.street.pk])), self.street.get_absolute_url())
        self.assertNotContains(self.client.get(self.street.get_absolute_url()), self.street.contact_phone)

    def test_street_submission_requires_photo_and_coordinates_but_no_phone(self):
        data=dict(placement='street', title='Оставленный стул', category=self.category.pk, description='Стул у скамейки, одна ножка немного шатается.', condition='good', district='central', latitude='69.349785', longitude='88.201376', pickup_address='У скамейки')
        form=ItemForm(data)
        self.assertFalse(form.is_valid())
        self.assertIn('photo', form.errors)
        form=ItemForm(data, {'photo':photo()})
        self.assertTrue(form.is_valid(),form.errors)
        item=services.submit_item(self.donor,form)
        self.assertEqual(item.status, Item.Status.AVAILABLE)
        self.assertEqual(item.contact_phone,'')
        self.assertGreater(item.expires_at, timezone.now()+timedelta(hours=5))

    def test_moderator_post_is_also_checked_automatically(self):
        data=dict(placement='home', title='Объявление со ссылкой', category=self.category.pk, description='Подробности по ссылке https://example.test/something', condition='good', district='central', pickup_address='Улица', contact_phone='+79001234567')
        form=ItemForm(data)
        self.assertTrue(form.is_valid(),form.errors)
        self.assertEqual(services.submit_item(self.coordinator,form).status,Item.Status.REVIEW)

    def test_presence_signals_are_disabled_but_complaints_still_work(self):
        from django.core.exceptions import ValidationError
        for kind in ('present', 'missing'):
            with self.assertRaises(ValidationError):
                services.signal_item(self.recipient, self.street.pk, kind)
        self.assertFalse(ItemSignal.objects.exists())
        services.signal_item(self.recipient, self.street.pk, 'unsafe')
        services.signal_item(self.other, self.street.pk, 'unsafe')
        self.street.refresh_from_db()
        self.assertEqual(self.street.status, Item.Status.REVIEW)

    def test_optional_details_default_to_unknown_without_moderation_penalty(self):
        form = ItemForm(dict(placement='home', title='Монитор', category=self.category.pk,
                            district='central', pickup_address='Адрес', contact_phone='+79001234567',
                            condition='', description=''))
        self.assertTrue(form.is_valid(), form.errors)
        item = services.submit_item(self.donor, form)
        self.assertEqual(item.condition, Item.Condition.UNKNOWN)
        self.assertEqual(item.description, '')
        self.assertEqual(item.status, Item.Status.AVAILABLE)

    def test_local_district_lookup_and_unknown_places(self):
        from apps.aid.districts import district_at
        for lat, lon, value in [(69.349,88.201,'central'), (69.5,88.4,'talnakh'),
                                (69.354,87.76,'kayerkan'), (69.358,88.38,'oganer')]:
            self.assertEqual(district_at(lat,lon),value)
        self.assertIsNone(district_at(55.75,37.62))

    def test_database_rejects_half_coordinate_pairs(self):
        with self.assertRaises(IntegrityError),transaction.atomic():
            Item.objects.filter(pk=self.home.pk).update(longitude=None)

    def test_editor_places_map_under_address_and_uses_explicit_controls(self):
        self.client.force_login(self.donor)
        response=self.client.get(reverse('item_create'))
        self.assertContains(response, 'data-location-picker')
        self.assertContains(response, 'Найти адрес на карте')
        self.assertContains(response, 'Обновить моё местоположение')
        self.assertLess(response.content.find(b'id_pickup_address'),response.content.find(b'data-location-picker'))

    @override_settings(CACHES={'default':{'BACKEND':'django.core.cache.backends.locmem.LocMemCache'},'geocoding':{'BACKEND':'django.core.cache.backends.locmem.LocMemCache','LOCATION':'test-geocoding'}})
    def test_geocoder_caches_and_paces_application_requests(self):
        from django.core.cache import caches
        caches['geocoding'].clear()
        response=MagicMock()
        response.__enter__.return_value.read.return_value=b'[{"lat":"69.3","lon":"88.2","display_name":"Street"}]'
        with patch('apps.aid.maps.urlopen',return_value=response) as upstream:
            url=reverse('map_address')
            self.assertEqual(self.client.get(url,{'q':'Street A'}).status_code,200)
            self.assertEqual(self.client.get(url,{'q':'Street A'}).status_code,200)
            self.assertEqual(self.client.get(url,{'q':'Street B'}).status_code,429)
            self.assertEqual(upstream.call_count,1)

    def test_help_page_describes_unattended_items_not_moderator_transfers(self):
        response=self.client.get(reverse('about'))
        self.assertContains(response,'Желающий может прийти и проверить вещь самостоятельно.')
        self.assertContains(response,'шесть часов')
        self.assertNotContains(response,'согласу')

    @override_settings(CACHES={'default':{'BACKEND':'django.core.cache.backends.locmem.LocMemCache'},'map_tiles':{'BACKEND':'django.core.cache.backends.locmem.LocMemCache','LOCATION':'test-map-tiles'}})
    def test_tile_proxy_keeps_cache_even_if_browser_requests_no_cache(self):
        from django.core.cache import caches
        caches['map_tiles'].clear()
        response=MagicMock()
        response.__enter__.return_value.read.return_value=b'\x89PNGtest-tile'
        response.__enter__.return_value.headers={'Cache-Control':'public, max-age=7200'}
        with patch('apps.aid.maps.urlopen',return_value=response) as upstream:
            url=reverse('map_tile',args=[12,2048,2048])
            first=self.client.get(url)
            self.assertEqual(first.status_code,200)
            self.assertIn(first['Cache-Control'], ['public, max-age=7200', 'public, max-age=7199'])
            self.assertEqual(self.client.get(url,HTTP_CACHE_CONTROL='no-cache').content,first.content)
            self.assertEqual(upstream.call_count,1)
        self.assertEqual(self.client.get(reverse('map_tile',args=[20,0,0])).status_code,404)

    def test_street_filter_and_anonymous_signal_return_to_item_after_login(self):
        response=self.client.get(reverse('catalog'), {'placement':'street'})
        self.assertContains(response,self.street.title)
        self.assertNotContains(response,self.home.title)
        response=self.client.get(self.street.get_absolute_url())
        self.assertContains(response,'Войти, чтобы пожаловаться')
        self.assertNotContains(response,'Ещё на месте')
        self.assertNotContains(response,'Уже нет')
        self.assertNotContains(response,'action="'+reverse('item_signal',args=[self.street.pk])+'"')

    def test_irrelevant_owner_contacts_are_ignored_for_street_posts(self):
        data=dict(placement='street',title='Стул у скамейки',category=self.category.pk,description='Оставленный стул у скамейки, состояние не проверял.',condition='unknown',district='central',latitude='69.349785',longitude='88.201376',donor_name='x'*200,contact_phone='not-a-phone')
        form=ItemForm(data,{'photo':photo()})
        self.assertTrue(form.is_valid(),form.errors)
        item=services.submit_item(self.donor,form)
        self.assertEqual(item.contact_phone,'')
        self.assertEqual(item.donor_name,'')

    def test_coarse_gps_needs_manual_refinement_for_street_post(self):
        data=dict(placement='street',title='Стул у скамейки',category=self.category.pk,description='Оставленный стул у скамейки, состояние не проверял.',condition='unknown',district='central',latitude='69.349785',longitude='88.201376',location_accuracy='5000')
        form=ItemForm(data,{'photo':photo()})
        self.assertFalse(form.is_valid())
        self.assertIn('pickup_address',form.errors)

    def test_form_can_derive_missing_district_from_coordinates(self):
        form = ItemForm(dict(placement='home', title='Монитор', category=self.category.pk,
                            latitude='69.5', longitude='88.4', contact_phone='+79001234567'))
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['district'], 'talnakh')

    def test_request_audit_excludes_secrets_and_query_values(self):
        import json
        from django.http import HttpResponse
        from django.test import RequestFactory
        from apps.aid.middleware import RequestAuditMiddleware
        request = RequestFactory().post('/account/login/?next=private-query', {'password': 'private-password'})
        request.user = self.recipient
        with patch('apps.aid.middleware.logger.info') as log:
            response = RequestAuditMiddleware(lambda r: HttpResponse(status=204))(request)
        self.assertEqual(response.status_code, 204)
        payload = log.call_args.args[0]
        self.assertNotIn('private-query', payload)
        self.assertNotIn('private-password', payload)
        self.assertEqual(json.loads(payload)['user_id'], self.recipient.pk)
        self.assertEqual(json.loads(payload)['status'], 204)
