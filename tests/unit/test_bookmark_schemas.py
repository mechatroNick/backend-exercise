"""Strict transport-contract tests for bookmark DTOs."""

from __future__ import annotations

from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import cast

import pytest
from pydantic import AnyHttpUrl, ValidationError

from app.bookmarks.schemas import (
    BookmarkCreate,
    BookmarkList,
    BookmarkPatch,
    BookmarkPublic,
    BookmarkQuery,
    TagPublic,
    _validate_url,
)


def create_payload(**changes: object) -> dict[str, object]:
    """Return a valid create payload with selected replacements."""
    payload: dict[str, object] = {
        "url": "https://Example.TEST/path",
        "title": "A precise title",
        "description": None,
        "tags": ["Python", " API "],
    }
    payload.update(changes)
    return payload


def test_create_canonicalizes_url_and_tags_from_a_json_array() -> None:
    bookmark = BookmarkCreate.model_validate(create_payload(tags=[" Python ", "api", "API"]))

    assert str(bookmark.url) == "https://example.test/path"
    assert bookmark.tags == ("api", "python")
    assert bookmark.description is None
    with pytest.raises(ValidationError):
        bookmark.title = "replacement"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("url", 1),
        ("title", 1),
        ("description", 1),
        ("tags", "python"),
        ("tags", [1]),
    ],
)
def test_create_rejects_type_coercion(field: str, value: object) -> None:
    with pytest.raises(ValidationError):
        BookmarkCreate.model_validate(create_payload(**{field: value}))


@pytest.mark.parametrize(
    "url",
    ["ftp://example.test", "/relative", "https://user@example.test", "https://u:p@example.test"],
)
def test_create_rejects_non_public_or_credential_bearing_urls(url: str) -> None:
    with pytest.raises(ValidationError):
        BookmarkCreate.model_validate(create_payload(url=url))


@pytest.mark.parametrize(
    "value",
    [
        SimpleNamespace(scheme="ftp", username=None, password=None),
        SimpleNamespace(scheme="https", username=None, password="secret"),
    ],
)
def test_url_defense_rejects_non_http_and_password_only_values(value: object) -> None:
    with pytest.raises(ValueError):
        _validate_url(cast(AnyHttpUrl, value))


@pytest.mark.parametrize(
    "title",
    ["", "   ", "x" * 201],
)
def test_create_rejects_invalid_titles_without_rewriting_valid_spelling(title: str) -> None:
    with pytest.raises(ValidationError):
        BookmarkCreate.model_validate(create_payload(title=title))

    preserved = BookmarkCreate.model_validate(create_payload(title="  MiXeD spelling  "))
    assert preserved.title == "  MiXeD spelling  "
    assert BookmarkCreate.model_validate(create_payload(title="x" * 200)).title == "x" * 200


@pytest.mark.parametrize("description", ["x" * 501, 1])
def test_create_description_has_exact_nullable_length_contract(description: object) -> None:
    with pytest.raises(ValidationError):
        BookmarkCreate.model_validate(create_payload(description=description))

    exact = " description "
    assert BookmarkCreate.model_validate(create_payload(description=exact)).description == exact
    assert (
        BookmarkCreate.model_validate(create_payload(description="x" * 500)).description
        == "x" * 500
    )


@pytest.mark.parametrize("tags", [[], ["   "], ["x" * 51]])
def test_create_requires_nonempty_valid_normalized_tags(tags: list[str]) -> None:
    with pytest.raises(ValidationError):
        BookmarkCreate.model_validate(create_payload(tags=tags))


def test_create_forbids_extras_and_request_models_have_exact_fields() -> None:
    with pytest.raises(ValidationError):
        BookmarkCreate.model_validate(create_payload(ignored=True))

    assert set(BookmarkCreate.model_fields) == {"url", "title", "description", "tags"}
    assert set(BookmarkPatch.model_fields) == {"url", "title", "description", "tags"}


@pytest.mark.parametrize(
    ("payload", "fields_set"),
    [({}, set()), ({"description": None}, {"description"}), ({"title": "new"}, {"title"})],
)
def test_patch_preserves_omitted_vs_description_null_semantics(
    payload: dict[str, object], fields_set: set[str]
) -> None:
    patch = BookmarkPatch.model_validate(payload)

    assert patch.model_fields_set == fields_set
    assert patch.description is None


@pytest.mark.parametrize("field", ["url", "title", "tags"])
def test_patch_rejects_explicit_null_for_non_clearable_fields(field: str) -> None:
    with pytest.raises(ValidationError):
        BookmarkPatch.model_validate({field: None})


def test_patch_validates_and_normalizes_the_same_contract_as_create() -> None:
    patch = BookmarkPatch.model_validate({"url": "http://EXAMPLE.test", "tags": [" Z ", "a", "A"]})

    assert str(patch.url) == "http://example.test/"
    assert patch.tags == ("a", "z")
    with pytest.raises(ValidationError):
        BookmarkPatch.model_validate({"tags": []})
    with pytest.raises(ValidationError):
        BookmarkPatch.model_validate({"url": "https://user@example.test"})


def test_public_models_are_frozen_exact_and_do_not_disclose_persistence_fields() -> None:
    instant = datetime(2026, 8, 6, 0, 0, tzinfo=UTC)
    public = BookmarkPublic(
        id=7,
        url="https://example.test/",
        title="Title",
        description=None,
        tags=(TagPublic(name="api"),),
        created_at=instant,
        updated_at=instant,
    )
    response = BookmarkList(items=(public,), total=1)

    assert public.model_dump(mode="json") == {
        "id": 7,
        "url": "https://example.test/",
        "title": "Title",
        "description": None,
        "tags": [{"name": "api"}],
        "created_at": "2026-08-06T00:00:00Z",
        "updated_at": "2026-08-06T00:00:00Z",
    }
    assert response.model_dump(mode="json")["page"] == 1
    assert response.model_dump(mode="json")["page_size"] == 20
    assert set(BookmarkPublic.model_fields) == {
        "id",
        "url",
        "title",
        "description",
        "tags",
        "created_at",
        "updated_at",
    }
    assert set(TagPublic.model_fields) == {"name"}
    assert not {"user_id", "tag_ids", "password", "created_by"} & set(BookmarkPublic.model_fields)
    with pytest.raises(ValidationError):
        public.id = 8  # type: ignore[misc]


def test_public_bookmark_id_must_be_positive() -> None:
    instant = datetime(2026, 8, 6, 0, 0, tzinfo=UTC)

    with pytest.raises(ValidationError):
        BookmarkPublic(
            id=0,
            url="https://example.test/",
            title="Title",
            description=None,
            tags=(),
            created_at=instant,
            updated_at=instant,
        )


@pytest.mark.parametrize("kwargs", [{"total": -1}, {"page": 0}, {"page_size": 101}])
def test_public_list_numeric_bounds_are_enforced(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        BookmarkList(items=(), **({"total": 0} | kwargs))


def test_query_defaults_aliases_canonical_tag_and_literal_query_content() -> None:
    query = BookmarkQuery.model_validate(
        {
            "tag": " Python ",
            "q": " %_\\ ",
            "from": "2026-08-01",
            "to": "2026-08-31",
            "updated_from": "2026-07-01",
            "updated_to": "2026-07-31",
            "page": "2",
            "page_size": "100",
        }
    )

    assert query.tag == "python"
    assert query.q == " %_\\ "
    assert query.created_from == date(2026, 8, 1)
    assert query.created_to == date(2026, 8, 31)
    assert query.page == 2
    assert query.page_size == 100
    assert query.model_dump(by_alias=True)["from"] == date(2026, 8, 1)
    assert "created_from" not in query.model_dump(by_alias=True)
    assert BookmarkQuery(created_from=date(2026, 8, 1)).created_from == date(2026, 8, 1)
    assert BookmarkQuery(page=2, page_size=3).page_size == 3
    assert BookmarkQuery().model_dump() == {
        "tag": None,
        "q": None,
        "created_from": None,
        "created_to": None,
        "updated_from": None,
        "updated_to": None,
        "page": 1,
        "page_size": 20,
    }
    with pytest.raises(ValidationError):
        query.page = 3  # type: ignore[misc]


@pytest.mark.parametrize("value", ["", 1, "x" * 201])
def test_query_rejects_invalid_literal_query_values(value: object) -> None:
    with pytest.raises(ValidationError):
        BookmarkQuery.model_validate({"q": value})


@pytest.mark.parametrize("tag", ["   ", "x" * 51, 1])
def test_query_reuses_canonical_tag_validation(tag: object) -> None:
    with pytest.raises(ValidationError):
        BookmarkQuery.model_validate({"tag": tag})


@pytest.mark.parametrize(
    "payload",
    [
        {"from": "2026-8-01"},
        {"from": "2026-08-1"},
        {"from": "2026-08-01T00:00:00Z"},
        {"from": datetime(2026, 8, 1, tzinfo=UTC)},
        {"from": "2026-02-30"},
        {"from": "２０２６-０８-０１"},
        {"from": "2026-08-02", "to": "2026-08-01"},
        {"updated_from": "2026-08-02", "updated_to": "2026-08-01"},
    ],
)
def test_query_rejects_noncanonical_or_reversed_dates(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        BookmarkQuery.model_validate(payload)


def test_query_accepts_open_date_ranges_and_forbids_extras() -> None:
    assert BookmarkQuery.model_validate({"from": "2026-08-01"}).created_to is None
    assert BookmarkQuery.model_validate({"updated_to": "2026-08-01"}).updated_from is None
    with pytest.raises(ValidationError):
        BookmarkQuery.model_validate({"unknown": "value"})


@pytest.mark.parametrize(
    "payload",
    [{"page": value} for value in [True, 1.0, "1.0", "1e1", "", " ", "١", "０", "-1", "0"]]
    + [{"page_size": value} for value in [True, 1.0, "1e1", "", " ", "١", "101", "0"]],
)
def test_query_rejects_coercive_or_out_of_range_pagination(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        BookmarkQuery.model_validate(payload)
