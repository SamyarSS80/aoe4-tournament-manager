import logging

from django.utils.translation import gettext_lazy as _
from django.http import Http404
from django.http.multipartparser import MultiPartParserError
from django.http.request import UnreadablePostError
from django.core.exceptions import (
    ValidationError as DjangoValidationError,
    SuspiciousOperation,
    PermissionDenied as DjangoPermissionDenied,
    ObjectDoesNotExist,
)

from rest_framework import status, exceptions
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.response import Response

try:
    import sentry_sdk
except Exception:
    sentry_sdk = None


SECURITY_LOGGER = logging.getLogger("django.security.SuspiciousOperation")
REQUEST_LOGGER = logging.getLogger("django.request")


def api_exception_handler(exc, context):
    if isinstance(exc, (SuspiciousOperation, SystemExit, KeyboardInterrupt)):
        raise

    if isinstance(exc, (UnreadablePostError, MultiPartParserError)):
        REQUEST_LOGGER.warning("Bad request body: %s", str(exc), exc_info=exc)
        return Response(
            {"code": status.HTTP_400_BAD_REQUEST, "errors": None, "message": "Bad request."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if isinstance(exc, DjangoPermissionDenied):
        return Response(
            {"code": status.HTTP_403_FORBIDDEN, "errors": None, "message": "Permission denied."},
            status=status.HTTP_403_FORBIDDEN,
        )

    if isinstance(exc, (Http404, ObjectDoesNotExist)):
        return Response(
            {"code": status.HTTP_404_NOT_FOUND, "errors": None, "message": _("Not found.")},
            status=status.HTTP_404_NOT_FOUND,
        )

    payload = {
        "code": status.HTTP_500_INTERNAL_SERVER_ERROR,
        "errors": None,
        "message": _("An unexpected error occurred."),
    }

    if isinstance(exc, DjangoValidationError):
        msgs = exc.messages
        payload["code"] = status.HTTP_400_BAD_REQUEST
        payload["errors"] = {"non_field_errors": msgs}
        payload["message"] = " ".join(map(str, msgs)) if msgs else _("Invalid input data.")

    elif isinstance(exc, DRFValidationError):
        detail = exc.detail
        payload["code"] = status.HTTP_400_BAD_REQUEST

        if isinstance(detail, list):
            payload["errors"] = []
            payload["message"] = " ".join(map(str, detail)) or _("Invalid input data.")
        else:
            payload["errors"] = detail if isinstance(detail, (dict, list)) else None
            payload["message"] = _("Invalid input data.") if isinstance(detail, (dict, list)) else str(detail)

    elif isinstance(
        exc,
        (
            exceptions.NotFound,
            exceptions.AuthenticationFailed,
            exceptions.PermissionDenied,
            exceptions.NotAuthenticated,
            exceptions.Throttled,
            exceptions.ParseError,
            exceptions.APIException,
        ),
    ):
        payload["code"] = getattr(exc, "status_code", status.HTTP_500_INTERNAL_SERVER_ERROR)
        detail = getattr(exc, "detail", None)

        if isinstance(detail, (dict, list)):
            payload["errors"] = detail
            payload["message"] = getattr(exc, "default_detail", _("Request error."))
        else:
            payload["message"] = str(detail) if detail is not None else _("Request error.")

        if payload["code"] >= 500:
            REQUEST_LOGGER.exception("APIException", exc_info=exc)
            if sentry_sdk:
                sentry_sdk.capture_exception(exc)

    else:
        REQUEST_LOGGER.exception("Unhandled exception", exc_info=exc)
        if sentry_sdk:
            sentry_sdk.capture_exception(exc)

    return Response(payload, status=payload["code"])
