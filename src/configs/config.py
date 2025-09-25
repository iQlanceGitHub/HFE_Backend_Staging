import os
from enum import Enum

from dotenv import load_dotenv

from src.common.logger import Logger

load_dotenv()


class EnvVar(Enum):
    DbHost = "DB_HOST"
    DbLocalHost = "DB_LOCAL_HOST"

    DbUser = "DB_USER"
    DbPassword = "DB_PASSWORD"
    DbName = "DB_NAME"

    QueueName = "QUEUE_NAME"

    MinPoolSize = "MIN_POOL_SIZE"
    MaxPoolSize = "MAX_POOL_SIZE"
    DbPort = "DB_PORT"
    LogLevel = "LOG_LEVEL"
    LogToFile = "LOG_TO_FILE"
    SecretKey = "SECRET_KEY"
    Algorithm = "ALGORITHM"
    AccessTokenExpireMinutes = "ACCESS_TOKEN_EXPIRE_MINUTES"
    GoogleApiKey = "GOOGLE_API_KEY"
    StripeAPIKey = "STRIPE_API_KEY"
    StripeWebhookSecret = "STRIPE_WEBHOOK_SECRET"


REQUIRED_VARS = [
    EnvVar.SecretKey.value,
    EnvVar.Algorithm.value,
    EnvVar.AccessTokenExpireMinutes.value,
    EnvVar.StripeAPIKey.value,
    EnvVar.StripeWebhookSecret.value,
]

OPTIONAL_VARS = [
    EnvVar.MinPoolSize.value,
    EnvVar.MaxPoolSize.value,
    EnvVar.DbPort.value,
    EnvVar.LogLevel.value,
    EnvVar.LogToFile.value,
    EnvVar.QueueName.value,
    EnvVar.DbHost.value,
    EnvVar.DbLocalHost.value,
    EnvVar.DbUser.value,
    EnvVar.DbPassword.value,
    EnvVar.DbName.value,
    EnvVar.GoogleApiKey.value,
]


class InvalidConfigurationError(Exception):
    """Raised when the configuration is invalid."""


def load_secrets():
    env_values = os.environ
    for key in REQUIRED_VARS:
        if key not in env_values:
            raise Exception(f"missing key: {key}")
        os.environ[key] = str(env_values[key])

    for key in OPTIONAL_VARS:
        value = env_values.get(key)
        if value is not None:
            os.environ[key] = str(value)
    try:
        os.environ[EnvVar.AccessTokenExpireMinutes.value] = str(
            int(os.environ[EnvVar.AccessTokenExpireMinutes.value])
        )
    except ValueError:
        raise InvalidConfigurationError(
            f"{EnvVar.AccessTokenExpireMinutes.value} must be an integer."
        )


load_secrets()

logger = Logger(
    level=os.environ.get(EnvVar.LogLevel.value, "INFO"),
    name="fast-api",
    log_to_file=True,
)
