from drf_spectacular.utils import extend_schema_view, extend_schema
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from common.permissions import IsAdminUser
from user.models import User
from user.serializers import UserSerializer, PublicUserSerializer, UsernamePasswordLoginSerializer, RegisterSerializer


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
