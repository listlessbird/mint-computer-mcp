import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from mint_computer_mcp.api.model import ApiModel


class Request(ApiModel):
    value: int


@given(value=st.integers())
def test_integer_round_trip(value: int) -> None:
    request = Request(value=value)
    assert Request.model_validate_json(request.model_dump_json()) == request


@pytest.mark.parametrize("value", ["123", 1.0, True, None])
def test_rejects_coercion(value: object) -> None:
    with pytest.raises(ValidationError) as error:
        _ = Request.model_validate({"value": value})
    assert error.value.errors()[0]["type"] == "int_type"


def test_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError) as error:
        _ = Request.model_validate({"value": 1, "typo": 2})
    assert error.value.errors()[0]["type"] == "extra_forbidden"


def test_rejects_reassignment() -> None:
    request = Request(value=1)
    with pytest.raises(ValidationError) as error:
        request.value = 2
    assert error.value.errors()[0]["type"] == "frozen_instance"
