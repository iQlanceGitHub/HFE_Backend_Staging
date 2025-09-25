import dataclasses as dc
from abc import ABC
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List

from src.common import labels
from src.common.utils import dc_to_dict, is_enum, is_list, is_subclass_of


@dataclass
class Dto(ABC):  # noqa: B024
    @classmethod
    def to_instance(cls, record: Dict[Any, Any]) -> "Dto":
        try:
            if not record:
                return None

            dto_props = dict()
            for f in dc.fields(cls):
                field = f.name
                v = record.get(field)
                if v is None:
                    continue

                if is_list(value=v):
                    list_type = f.type.__args__[0]
                    if (
                        v
                        and is_subclass_of(list_type, Dto)
                        and not isinstance(v[0], Dto)
                    ):
                        dto_props[field] = list_type.to_instance_records(records=v)
                    elif (
                        v
                        and not is_enum(value=v[0])
                        and is_subclass_of(list_type, Enum)
                    ):
                        dto_props[field] = [list_type[e] for e in v]
                    else:
                        dto_props[field] = v
                elif is_subclass_of(f.type, Dto) and not isinstance(v, Dto):
                    dto_props[field] = f.type.to_instance(v)
                elif not is_enum(value=v) and is_subclass_of(f.type, Enum):
                    dto_props[field] = f.type[v]
                elif is_enum(value=v) and not is_subclass_of(f.type, Enum):
                    dto_props[field] = v.value
                else:
                    dto_props[field] = v

            return cls(**dto_props)
        except Exception as e:
            raise Exception(
                f"{labels.ErrorConvertingToDataclassInstance} - {cls.__name__}: {e}"
            )

    @classmethod
    def to_instance_records(cls, records: List[Dict[Any, Any]]) -> List["Dto"]:
        return [cls.to_instance(record=r) for r in records]

    def dto_to_dict(self) -> Dict[str, Any]:
        return dc_to_dict(obj=self)
