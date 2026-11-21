from django.db import migrations


def forward(apps, schema_editor):
    Contact = apps.get_model('aid', 'Contact')
    for model_name, name_field in [('Item', 'donor_name'), ('HelpRequest', 'recipient_name')]:
        Model = apps.get_model('aid', model_name)
        for obj in Model.objects.using(schema_editor.connection.alias).all().iterator():
            contact, _ = Contact.objects.using(schema_editor.connection.alias).get_or_create(name=getattr(obj, name_field), phone=obj.contact_phone)
            obj.contact_id = contact.pk
            fields = ['contact']
            if model_name == 'HelpRequest':
                obj.unselected_category_id = obj.category_id if obj.preferred_item_id is None else None
                fields.append('unselected_category')
            obj.save(update_fields=fields)


def reverse(apps, schema_editor):
    for model_name, name_field in [('Item', 'donor_name'), ('HelpRequest', 'recipient_name')]:
        Model = apps.get_model('aid', model_name)
        for obj in Model.objects.using(schema_editor.connection.alias).select_related('contact').all().iterator():
            setattr(obj, name_field, obj.contact.name)
            obj.contact_phone = obj.contact.phone
            fields = [name_field, 'contact_phone']
            if model_name == 'HelpRequest':
                obj.category_id = obj.preferred_item.category_id if obj.preferred_item_id else obj.unselected_category_id
                fields.append('category')
            obj.save(update_fields=fields)


class Migration(migrations.Migration):
    dependencies = [('aid', '0003_normalized_contacts')]
    operations = [migrations.RunPython(forward, reverse)]
