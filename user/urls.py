from rest_framework.routers import DefaultRouter
from user.views import UserViewSet, AuthenticationView

router = DefaultRouter()

router.register("users", UserViewSet, basename="users")

router.register("authentication", AuthenticationView, basename="authentication")

urlpatterns = router.urls
