"""Pinned Schemathesis ASGI smoke generation for authenticated safe GET operations."""

from __future__ import annotations

import pytest
import schemathesis
from hypothesis import settings

from tests.contract.test_runtime_contract import _headers, _register

pytest_plugins = ("tests.contract.test_runtime_contract",)


@pytest.fixture
def api_schema(contract_client):
    return schemathesis.openapi.from_asgi("/openapi.json", contract_client.app)


@pytest.fixture
def schemathesis_token(contract_client) -> str:
    return _register(contract_client)


schema = schemathesis.pytest.from_fixture("api_schema").include(
    method="GET", path_regex=r"^/api/bookmarks(?:/stats|/\{bookmark_id\})?$"
)
_SAFE_GET_PATHS = {
    "/api/bookmarks",
    "/api/bookmarks/stats",
    "/api/bookmarks/{bookmark_id}",
}


@pytest.fixture(scope="session")
def generated_get_ledger() -> set[str]:
    ledger: set[str] = set()
    yield ledger
    assert ledger == _SAFE_GET_PATHS


@pytest.mark.mandatory
@schema.parametrize()
@settings(max_examples=3, derandomize=True, deadline=None)
def test_safe_authenticated_gets(case, schemathesis_token: str, generated_get_ledger: set[str]):
    assert case.method == "GET"
    generated_get_ledger.add(case.operation.path)
    response = case.call(
        headers=_headers(schemathesis_token),
        params={key: value for key, value in case.query.items() if value is not None},
    )
    case.validate_response(response)
