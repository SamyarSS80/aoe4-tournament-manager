from rest_framework.routers import DefaultRouter

from .views import AoeWorldPublicViewSet

router = DefaultRouter()

router.register(r"aoe-world/public", AoeWorldPublicViewSet, basename="aoe-world-public")

urlpatterns = router.urls
