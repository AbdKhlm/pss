from jwt.exceptions import PyJWTError
from ninja.errors import AuthenticationError
from ninja_simple_jwt.auth.ninja_auth import HttpJwtAuth
from ninja_simple_jwt.jwt.token_operations import TokenTypes, decode_token
from ninja_simple_jwt.settings import ninja_simple_jwt_settings


class SwaggerFriendlyJwtAuth(HttpJwtAuth):
    @staticmethod
    def normalize_token(token: str) -> str:
        normalized = token.strip().strip('"').strip("'").rstrip(",")

        if normalized.lower().startswith("bearer "):
            normalized = normalized.split(" ", 1)[1].strip()

        return "".join(normalized.split())

    def authenticate(self, request, token: str) -> bool:
        token = self.normalize_token(token)

        try:
            decoded_token = decode_token(token, token_type=TokenTypes.ACCESS, verify=True)

            user_id = decoded_token.get("user_id")
            if not user_id:
                raise AuthenticationError(status_code=401, message="Invalid token: missing user_id")

            if ninja_simple_jwt_settings.USE_STATELESS_AUTH:
                user = self._create_stateless_user(decoded_token)
            else:
                user = self._get_user_from_database(user_id)
                if user is None:
                    raise AuthenticationError(status_code=401, message="Invalid or expired token")

            request.user = user  # type: ignore[assignment]
            return True

        except PyJWTError as e:
            raise AuthenticationError(
                status_code=401,
                message=(
                    "Invalid or expired token. Use the full access token from /auth/login "
                    "and paste only the token value into Swagger Authorize."
                ),
            ) from e
