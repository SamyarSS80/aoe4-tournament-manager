class JWTException(Exception):
    pass


class DecodeError(JWTException):
    pass


class InvalidTokenError(JWTException):
    pass


class ExpiredSignatureError(JWTException):
    pass
