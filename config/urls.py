from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('account/', include('apps.accounts.urls')),
    path('', include('apps.aid.urls')),
]
handler403 = 'apps.aid.views.error403'
handler404 = 'apps.aid.views.error404'
handler500 = 'apps.aid.views.error500'
