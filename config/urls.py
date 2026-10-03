from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path


def devtools_probe(request):
    return HttpResponse("{}", content_type="application/json")


urlpatterns = [
    path("admin/", admin.site.urls),
    path(".well-known/appspecific/com.chrome.devtools.json", devtools_probe),
    path("", include("interview.urls")),
]
