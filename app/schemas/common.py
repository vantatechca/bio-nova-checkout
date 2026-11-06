from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints
from pydantic.alias_generators import to_camel


class CamelModel(BaseModel):
    """Model whose JSON keys are camelCase (settings screens) but can be built from snake_case."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


def _text(max_length: int):
    return Annotated[str, StringConstraints(strip_whitespace=True, max_length=max_length)]


# Whitespace-stripped, length-limited strings.
Text20 = _text(20)
Text40 = _text(40)
Text80 = _text(80)
Text100 = _text(100)
Text200 = _text(200)
Text300 = _text(300)
Text500 = _text(500)
Text1000 = _text(1000)
Text2000 = _text(2000)
