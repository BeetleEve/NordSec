from getpass import getpass
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from apps.accounts.models import User


class Command(BaseCommand):
    help = 'Создать аккаунт: create_account ЛОГИН ПАРОЛЬ РОЛЬ. Роли: member, volunteer, moderator.'

    def add_arguments(self, parser):
        parser.add_argument('login')
        parser.add_argument('password', nargs='?', help='Если пропущен, вводится скрыто; роль задайте через --role.')
        parser.add_argument('privilege', nargs='?', choices=['member', 'volunteer', 'moderator'])
        parser.add_argument('--role', choices=['member', 'volunteer', 'moderator'])

    def handle(self, *args, **options):
        role = options['privilege'] or options['role']
        if role is None:
            raise CommandError('Укажите роль: member, volunteer или moderator.')
        if User.objects.filter(username=options['login']).exists():
            raise CommandError('Такой логин уже существует. Аккаунт не изменён.')
        user = User(username=options['login'], role=role)
        password = options['password'] or getpass('Пароль: ')
        try:
            user.full_clean(exclude=['password'])
            validate_password(password, user)
        except ValidationError as exc:
            raise CommandError('; '.join(exc.messages))
        user.set_password(password)
        user.save()
        self.stdout.write(self.style.SUCCESS(f'Создан аккаунт {user.username}; роль: {user.get_role_display()}.'))
