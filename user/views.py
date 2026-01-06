from drf_spectacular.utils import extend_schema_view, extend_schema
from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from common.permissions import IsAdminUser
from user.models import User, UserAvailability
from user.serializers import UserSerializer, PublicUserSerializer, UsernamePasswordLoginSerializer, RegisterSerializer, \
                             UserAvailabilitySerializer
from user.services import UserAvailabilityService


@extend_schema_view(
    login=extend_schema(
        summary="Login (username/password)",
        description="Login with username and password and receive access + refresh JWT tokens.",
        request=UsernamePasswordLoginSerializer,
        responses={200: None, 400: None},
        tags=["Authentication"],
    ),
    register=extend_schema(
        summary="Register",
        description="Register a new user (public). No tokens are returned here.",
        request=RegisterSerializer,
        responses={201: PublicUserSerializer, 400: None},
        tags=["Authentication"],
    ),
)
class AuthenticationView(GenericViewSet):
    permission_classes = [AllowAny]

    def get_queryset(self):
        return None

    @action(methods=["post"], detail=False, url_path="login")
    def login(self, request):
        serializer = UsernamePasswordLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data)

    @action(methods=["post"], detail=False, url_path="register")
    def register(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.save()

        return Response(PublicUserSerializer(user).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    list=extend_schema(
        summary="List users",
        tags=["Users"],
    ),
    retrieve=extend_schema(
        summary="Retrieve user",
        tags=["Users"],
    ),
    update=extend_schema(
        summary="Update user",
        tags=["Users"],
    ),
    partial_update=extend_schema(
        summary="Partial update user",
        tags=["Users"],
    ),
    destroy=extend_schema(
        summary="Delete user",
        tags=["Users"],
    ),
    info=extend_schema(
        summary="Current user info",
        tags=["Users"],
        responses={200: PublicUserSerializer},
    ),
)
class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    queryset = User.objects.all().order_by("-id")
    http_method_names = ["get", "put", "patch", "delete", "head", "options"]

    def get_permissions(self):
        if self.action in {"list", "retrieve", "update", "partial_update", "destroy"}:
            return [IsAuthenticated(), IsAdminUser()]

        return [IsAuthenticated()]

    @action(detail=False, methods=["get"], url_path="info")
    def info(self, request, *args, **kwargs):
        return Response(PublicUserSerializer(request.user).data, status=status.HTTP_200_OK)


@extend_schema_view(
    list=extend_schema(summary="List my availability", tags=["User Availability"]),
    retrieve=extend_schema(summary="Availability details", tags=["User Availability"]),
    create=extend_schema(summary="Create availability", tags=["User Availability"]),
    update=extend_schema(summary="Update availability", tags=["User Availability"]),
    partial_update=extend_schema(summary="Update availability (PATCH)", tags=["User Availability"]),
    destroy=extend_schema(summary="Delete availability", tags=["User Availability"]),
)
class UserAvailabilityViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = UserAvailabilitySerializer

    def get_queryset(self):
        return UserAvailability.objects.filter(user=self.request.user).order_by("start_offset", "id")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        obj, created = UserAvailabilityService.create_or_merge(
            user=request.user,
            start_day=serializer.validated_data["start_day"],
            start_time=serializer.validated_data["start_time"],
            end_day=serializer.validated_data["end_day"],
            end_time=serializer.validated_data["end_time"],
        )

        out = self.get_serializer(obj).data
        return Response(out, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()

        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        obj, _created = UserAvailabilityService.create_or_merge(
            user=request.user,
            start_day=serializer.validated_data.get("start_day", instance.start_day),
            start_time=serializer.validated_data.get("start_time", instance.start_time),
            end_day=serializer.validated_data.get("end_day", instance.end_day),
            end_time=serializer.validated_data.get("end_time", instance.end_time),
            instance_id=instance.id,
        )

        out = self.get_serializer(obj).data
        return Response(out, status=status.HTTP_200_OK)