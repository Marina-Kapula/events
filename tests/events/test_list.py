from collections.abc import Callable
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.test import Client
from pytest_django import DjangoAssertNumQueries

from accounts.models import User
from events.models import Event, Size

pytestmark = pytest.mark.django_db

NOW = datetime(2027, 3, 1, 12, 0, tzinfo=ZoneInfo("Europe/Rome"))


def test_listed_is_approved_or_pending_and_not_started_soonest_first(
    make_event: Callable[..., Event],
) -> None:
    make_event(title="Later", starts_at=NOW + timedelta(days=2))
    make_event(title="Sooner", starts_at=NOW + timedelta(days=1))
    make_event(title="Started", starts_at=NOW - timedelta(minutes=1))
    make_event(
        title="Pending", starts_at=NOW + timedelta(days=3), status=Event.Status.PENDING
    )
    for status in (Event.Status.REJECTED, Event.Status.CANCELLED):
        make_event(starts_at=NOW + timedelta(days=1), status=status)

    listed = Event.objects.listed(now=NOW)

    assert [event.title for event in listed] == ["Sooner", "Later", "Pending"]


def test_a_pending_event_is_listed_as_not_approved_yet(
    client: Client, make_student: Callable[..., User], make_event: Callable[..., Event]
) -> None:
    make_event(status=Event.Status.PENDING)
    client.force_login(make_student())

    assert b"Not approved yet" in client.get("/").content


def test_search_looks_in_title_and_description(
    make_event: Callable[..., Event],
) -> None:
    make_event(title="Pizza night")
    make_event(title="Hike", description="Bring PIZZA for lunch.")
    make_event(title="Museum")

    found = Event.objects.search("pizza")

    assert {event.title for event in found} == {"Pizza night", "Hike"}


def test_in_city_matches_part_of_the_name(make_event: Callable[..., Event]) -> None:
    make_event(title="Here", city="Avezzano")
    make_event(title="There", city="Roma")

    assert [event.title for event in Event.objects.in_city("avez")] == ["Here"]


def test_on_date_uses_the_local_day(make_event: Callable[..., Event]) -> None:
    rome = NOW.tzinfo
    make_event(title="Evening", starts_at=datetime(2027, 3, 5, 21, 0, tzinfo=rome))
    # 00:30 in Rome is still 23:30 of the day before in UTC.
    make_event(title="Late", starts_at=datetime(2027, 3, 6, 0, 30, tzinfo=rome))

    found = Event.objects.on_date(day=date(2027, 3, 5))

    assert [event.title for event in found] == ["Evening"]


def test_of_type(make_event: Callable[..., Event]) -> None:
    make_event(title="Pizza", type=Event.Type.FOOD)
    make_event(title="Hike", type=Event.Type.TRIP)

    assert [event.title for event in Event.objects.of_type("trip")] == ["Hike"]


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (Size.SMALL, {"2", "5"}),
        (Size.MEDIUM, {"6", "10"}),
        (Size.LARGE, {"11", "100"}),
    ],
)
def test_of_size(
    make_event: Callable[..., Event], size: Size, expected: set[str]
) -> None:
    for max_people in (2, 5, 6, 10, 11, 100):
        make_event(title=str(max_people), max_people=max_people)

    assert {event.title for event in Event.objects.of_size(size)} == expected


def test_the_list_page_filters_with_get(
    client: Client, make_student: Callable[..., User], make_event: Callable[..., Event]
) -> None:
    make_event(title="Pizza night", city="Avezzano")
    make_event(title="Pizza in Rome", city="Roma")
    client.force_login(make_student())

    response = client.get("/", {"q": "pizza", "city": "roma"})

    assert response.status_code == 200
    assert b"Pizza in Rome" in response.content
    assert b"Pizza night" not in response.content


def test_a_wrong_filter_value_shows_an_error(
    client: Client, make_student: Callable[..., User], make_event: Callable[..., Event]
) -> None:
    make_event(title="Pizza night")
    client.force_login(make_student())

    response = client.get("/", {"size": "huge"})

    assert b"Select a valid choice" in response.content
    assert b"Pizza night" in response.content


def test_the_list_page_runs_a_fixed_number_of_queries(
    client: Client,
    make_student: Callable[..., User],
    make_event: Callable[..., Event],
    django_assert_num_queries: DjangoAssertNumQueries,
) -> None:
    for _ in range(3):
        make_event()
    client.force_login(make_student())

    # The session, the logged-in user, and the events: however many events there are.
    with django_assert_num_queries(3):
        response = client.get("/")

    assert response.content.count(b"<article") == 3
