from django.db import migrations
from django.db.models import F


def reorder(apps, schema_editor):
    Category = apps.get_model('aid', 'Category')
    other = Category.objects.filter(slug='other').first()
    tech = Category.objects.filter(name='Техника').first()
    if other and tech and tech.order >= other.order:
        position = other.order
        Category.objects.filter(order__gte=position).exclude(pk=tech.pk).update(order=F('order')+1)
        Category.objects.filter(pk=tech.pk).update(order=position)


class Migration(migrations.Migration):
    dependencies = [('aid', '0011_optional_listing_details_and_tech_category')]
    operations = [migrations.RunPython(reorder, migrations.RunPython.noop)]
