from rest_framework.routers import DefaultRouter
from jwt_token.views import JsonWebTokenView

router = DefaultRouter()
router.register("", JsonWebTokenView, basename="jwt")

urlpatterns = router.urls
