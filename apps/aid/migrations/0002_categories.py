from django.db import migrations


def populate(apps, schema_editor):
    Category = apps.get_model('aid', 'Category')
    for order, (name, slug) in enumerate([
        ('Одежда и обувь', 'clothes'), ('Детские вещи', 'children'),
        ('Для дома', 'home'), ('Мебель', 'furniture'), ('Книги', 'books'), ('Другое', 'other'),
    ]):
        Category.objects.get_or_create(slug=slug, defaults={'name': name, 'illustration': slug, 'order': order})


class Migration(migrations.Migration):
    dependencies = [('aid', '0001_initial')]
    operations = [migrations.RunPython(populate, migrations.RunPython.noop)]
