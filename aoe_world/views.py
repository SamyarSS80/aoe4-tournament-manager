from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response
from drf_spectacular.utils import OpenApiParameter, OpenApiTypes, extend_schema, extend_schema_view

from .serializers import AoeWorldPlayerCodeInputSerializer, AoeWorldPlayerDetailsSerializer
from .services import AoeWorldAPIService


@extend_schema_view(
    player_details=extend_schema(
        summary="Get AoE4World player details by code (profile_id)",
        parameters=[
            OpenApiParameter(
                name="code",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.QUERY,
                required=True,
                description="AoE4World profile_id (numeric).",
            ),
        ],
        responses={200: AoeWorldPlayerDetailsSerializer},
        tags=["AoE4World Public"],
    ),
)
class AoeWorldPublicViewSet(viewsets.GenericViewSet):
    permission_classes = [permissions.AllowAny]
    authentication_classes = []

    @action(detail=False, methods=["get"], url_path="player-details")
    def player_details(self, request, *args, **kwargs):
        params = AoeWorldPlayerCodeInputSerializer(data=request.query_params)
        params.is_valid(raise_exception=True)

        data = AoeWorldAPIService.get_player_details(code=params.validated_data["code"])
        ser = AoeWorldPlayerDetailsSerializer(instance=data, context={"request": request})
        return Response(ser.data, status=status.HTTP_200_OK)
