from drf_spectacular.utils import extend_schema_view, extend_schema
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from jwt_token import serializers


@extend_schema_view(
    verify=extend_schema(
        summary="Verify JWT token",
        request=serializers.JsonWebTokenSerializer,
        responses={200: serializers.JsonWebTokenSerializer, 400: None},
        tags=["JWT"],
    ),
    refresh=extend_schema(
        summary="Refresh JWT token",
        request=serializers.JsonWebTokenRefreshSerializer,
        responses={200: serializers.JsonWebTokenRefreshSerializer, 400: None},
        tags=["JWT"],
    ),
)
class JsonWebTokenView(GenericViewSet):
    permission_classes = [AllowAny]

    def get_queryset(self):
        return None

    @action(methods=["post"], detail=False, url_path="verify", serializer_class=serializers.JsonWebTokenSerializer)
    def verify(self, request):
        ser = serializers.JsonWebTokenSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        return Response(ser.validated_data)

    @action(methods=["post"], detail=False, url_path="refresh", serializer_class=serializers.JsonWebTokenRefreshSerializer)
    def refresh(self, request):
        ser = serializers.JsonWebTokenRefreshSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        return Response(ser.validated_data)
