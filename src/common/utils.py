import asyncio
import pickle
import uuid
from dataclasses import asdict, dataclass, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any, Callable, Dict


def is_courotine(func: Callable) -> bool:
    return asyncio.iscoroutinefunction(func=func)


def is_subclass_of(subclass: type, class_type: Any) -> bool:
    return isinstance(subclass, type) and issubclass(subclass, class_type)


def is_enum(value: Any) -> bool:
    return isinstance(value, Enum)


def is_list(value: Any) -> bool:
    return isinstance(value, list)


def is_bytes(value: Any) -> bool:
    return isinstance(value, bytes)


def bytes_to_str(content: bytes) -> str:
    return content.decode("utf-8")


def bytes_to_dict(content: bytes) -> dict:
    return pickle.loads(content)  # noqa: S301


def from_bytes(bytes_content: bytes) -> str | dict:
    try:
        return bytes_to_str(content=bytes_content)
    except Exception:
        return bytes_to_dict(content=bytes_content)


def is_exception(value: Any) -> bool:
    return isinstance(value, Exception)


def is_uuid(value: Any) -> bool:
    return isinstance(value, uuid.UUID)


def is_datetime(value: Any) -> bool:
    return isinstance(value, date | datetime)


def is_dict(value: Any) -> bool:
    return isinstance(value, dict)


def convert_value(v: Any) -> Any:  # noqa: PLR0911
    if is_enum(value=v):
        return v.value
    if is_bytes(value=v):
        return from_bytes(bytes_content=v)
    if is_dataclass(obj=v):
        return dc_to_dict(obj=v)
    if is_exception(value=v) or is_uuid(value=v):
        return str(v)
    if is_datetime(value=v):
        return v.strftime("%m/%d/%Y, %H:%M:%S")
    if is_list(value=v):
        return [convert_value(o) for o in v]
    if is_dict(value=v):
        return {k: convert_value(cv) for k, cv in v.items()}

    return v


def custom_asdict_factory(data: Any) -> Dict:
    return {k: convert_value(v) for k, v in data}


def dc_to_dict(obj: dataclass) -> Dict[str, Any]:
    return asdict(obj, dict_factory=custom_asdict_factory)


def is_primitive(value: Any) -> bool:
    return isinstance(value, int | str | bool | float | bytes)


def is_class(value: Any) -> bool:
    return (
        value is not None
        and hasattr(value, "__class__")
        and not is_primitive(value=value)
        and not is_dataclass(obj=value)
        and not is_exception(value=value)
    )


def process_nested_dict(data: dict) -> Dict[str, Any]:
    processed_dict = dict()

    for k, v in data.items():
        if is_dict(value=v):
            processed_dict[k] = process_nested_dict(data=v)
        elif is_list(value=v):
            processed_list = list()
            for o in v:
                if is_dict(value=o):
                    processed_list.append(process_nested_dict(data=o))
                elif is_class(value=o):
                    processed_list.append(convert_value(v=dict(o)))
                else:
                    processed_list.append(convert_value(v=o))
            processed_dict[k] = processed_list
        elif is_class(value=v):
            processed_dict[k] = process_nested_dict(data=dict(v))
        else:
            processed_dict[k] = convert_value(v=v)

    return processed_dict
