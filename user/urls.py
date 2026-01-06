from rest_framework.routers import DefaultRouter
from user.views import UserViewSet, AuthenticationView, UserAvailabilityViewSet

router = DefaultRouter()

router.register("users", UserViewSet, basename="users")

router.register("authentication", AuthenticationView, basename="authentication")

router.register("availabilities", UserAvailabilityViewSet, basename="availabilities")

urlpatterns = router.urls
