from decimal import Decimal
from typing import Any

from bson import Decimal128 as _Decimal128
from pydantic import GetCoreSchemaHandler, GetJsonSchemaHandler
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema


class PydanticDecimal128(_Decimal128):
    """"""

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source: type[Any], _handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.json_or_python_schema(
            python_schema=core_schema.with_info_plain_validator_function(cls._validate),
            json_schema=core_schema.str_schema(),
            serialization=core_schema.plain_serializer_function_ser_schema(
                lambda instance: str(instance)
            ),
        )

    @classmethod
    def __get_pydantic_json_schema__(
        cls, schema: core_schema.CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        json_schema = handler(schema)
        json_schema.update(
            pattern=r"^[+-]?(\d+(\.\d*)?|\.\d+)$",
            type="string",
            example="12.34",
        )
        return json_schema

    @classmethod
    def _validate(cls, v, _: core_schema.ValidationInfo):
        if isinstance(v, _Decimal128):
            return v
        return cls(Decimal(v))
