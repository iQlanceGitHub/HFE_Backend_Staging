import logging
import sys
from dataclasses import InitVar, dataclass, field
from typing import Optional

from src.common.utils import process_nested_dict


@dataclass
class Logger:
    level: InitVar[int] = logging.INFO
    name: InitVar[Optional[str]] = None
    log_to_file: InitVar[bool] = False
    __logger: logging.Logger = field(init=False)

    def __post_init__(self, level: int, name: Optional[str], log_to_file: bool):
        logger_name = name if name else __name__
        self.__logger = logging.getLogger(logger_name)
        self.__logger.setLevel(level)

        if not self.__logger.handlers:
            formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

            # Stream Handler
            stream_handler = logging.StreamHandler(sys.stdout)
            stream_handler.setFormatter(formatter)
            self.__logger.addHandler(stream_handler)

            # File Handler if logging to file is enabled
            if log_to_file:
                file_handler = logging.FileHandler("test_log.log")
                file_handler.setFormatter(formatter)
                self.__logger.addHandler(file_handler)

    @property
    def logger(self) -> logging.Logger:
        return self.__logger

    def add_handler(self, handler: logging.Handler):
        self.__logger.addHandler(handler)

    def log_error(
        self,
        msg: str,
        tag: Optional[str] = None,
        details: Optional[dict] = None,
        *args,
        **kwargs,
    ):
        self.log(
            msg=msg, tag=tag, level=logging.ERROR, details=details, *args, **kwargs
        )

    def log_warning(
        self,
        msg: str,
        tag: Optional[str] = None,
        details: Optional[dict] = None,
        *args,
        **kwargs,
    ):
        self.log(
            msg=msg, tag=tag, level=logging.WARNING, details=details, *args, **kwargs
        )

    def log_debug(
        self,
        msg: str,
        tag: Optional[str] = None,
        details: Optional[dict] = None,
        *args,
        **kwargs,
    ):
        self.log(
            msg=msg, tag=tag, level=logging.DEBUG, details=details, *args, **kwargs
        )

    def log_info(
        self,
        msg: str,
        tag: Optional[str] = None,
        details: Optional[dict] = None,
        *args,
        **kwargs,
    ):
        self.log(msg=msg, tag=tag, level=logging.INFO, details=details, *args, **kwargs)

    def log(
        self,
        msg: str,
        tag: Optional[str] = None,
        level=logging.INFO,
        details: Optional[dict] = None,
        *args,
        **kwargs,
    ):
        if level < self.__logger.level:
            return

        if tag:
            msg = f"[{tag}] - {msg}"

        try:
            details = details or {}

            # Include any args/kwargs passed for transparency
            if args:
                details["args"] = [repr(arg) for arg in args]
            if kwargs:
                details["kwargs"] = {k: repr(v) for k, v in kwargs.items()}

            # Process nested dict if needed
            details = process_nested_dict(details)

            if self.__logger.name:
                details["component"] = self.__logger.name

            self.__logger.log(level, msg, extra=details)
        except KeyError as e:
            self.log_debug(
                msg=f"Logging details include reserved logging args: {e}! Replacing them ..."
            )
            self.__logger.log(
                level, msg, extra=self.__handle_logging_reserved_args(details)
            )
        except Exception as e:
            self.__logger.info(f"Error Logging: {e}")

    def __handle_logging_reserved_args(self, details: dict) -> dict:
        reserved_keys = {"name", "lineno", "message", "msg"}
        for key in reserved_keys:
            if key in details:
                details[f"_{key}"] = details.pop(key)
        return details
