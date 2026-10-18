"""Offline tests for the OpenStreetMap / Overpass layer.

Overpass is free, but it is a shared community service: a suite that hit it on
every run would be slow, flaky and rude. So nothing here touches the network -
the query we build, the way we identify ourselves, and how a real Overpass
response is turned into places are all checked against a fake transport. What
these tests cannot check is whether Overpass is *reachable* from this machine -
that is scripts/places_smoke.py's job, by hand, once.

The sample elements below are trimmed copies of real Overpass output for Kannur
town centre, so the tests are shaped by the data that actually exists there.
"""
import pytest
import requests

from app import places

# A real node: amenity=clinic with a name, no address tags, no speciality tag.
NODE = {"type": "node", "id": 5166902095, "lat": 11.870804, "lon": 75.367665,
        "tags": {"amenity": "clinic", "healthcare": "clinic",
                 "name": "Railway Station Health Unit",
                 "operator": "southern railway"}}
# A way: no lat/lon of its own, so `out center` is what makes it scoreable.
WAY = {"type": "way", "id": 123456789, "center": {"lat": 11.876, "lon": 75.372},
       "tags": {"amenity": "doctors",
                "healthcare:speciality": "gastroenterology;hepatology",
                "name": "Kannur Gastro Care",
                "contact:phone": "+91 497 1234567",
                "opening_hours": "Mo-Sa 09:00-17:00"}}
# A way whose geometry Overpass could not reduce to a centre.
NO_CENTRE = {"type": "way", "id": 999, "tags": {"amenity": "clinic"}}


class FakeResponse:
    """The bits of requests.Response that app/places.py actually uses."""

    def __init__(self, payload=None, status_code=200, text=""):
        self._payload = payload if payload is not None else {}
        self.status_code = status_code
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error",
                                     response=self)

    def json(self):
        return self._payload


@pytest.fixture
def sent_request(monkeypatch):
    """Capture the request app/places.py would send, and answer it locally."""
    captured = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return FakeResponse({"elements": [NODE, WAY]})

    monkeypatch.setattr(places.requests, "post", fake_post)
    return captured


def test_the_query_asks_for_doctors_and_clinics_around_the_point(sent_request):
    places.find_doctors("Gastroenterologist", 11.8745, 75.3704, radius=8000)

    query = sent_request["data"]["data"]
    assert sent_request["url"] == places.URL
    assert "[out:json]" in query
    assert "(around:8000,11.8745,75.3704)" in query
    # amenity=doctor does not exist in the OSM schema: the value is "doctors".
    # Every filter in DOCTOR_FILTERS has to be in the query, because a facility
    # often carries only one of these tags.
    for key, value in places.DOCTOR_FILTERS:
        assert f'nwr["{key}"="{value}"]' in query
    # Ways and relations have no lat/lon of their own, so without this they
    # would come back unscorable.
    assert "out center;" in query


def test_it_identifies_itself_to_overpass(sent_request):
    places.find_doctors("Gastroenterologist", 11.8745, 75.3704)

    # Overpass throttles anonymous clients, and its usage policy asks for a
    # User-Agent that says who is calling.
    agent = sent_request["headers"]["User-Agent"]
    assert agent.startswith("CureConnect/")
    assert "python-requests" not in agent
    assert sent_request["headers"]["Accept"] == "application/json"


def test_the_client_timeout_outlives_the_server_side_one(sent_request):
    places.find_doctors("Gastroenterologist", 11.8745, 75.3704)

    # [timeout:25] is what the query asks the server for, so a client timeout
    # at or below it would throw away work the server had already done.
    assert sent_request["timeout"] > places.SERVER_TIMEOUT_S


def test_a_node_and_a_way_both_become_scoreable_places(sent_request):
    found = places.find_doctors("Gastroenterologist", 11.8745, 75.3704)
    by_name = {place["displayName"]["text"]: place for place in found}
    assert len(found) == 2

    node = by_name["Railway Station Health Unit"]
    assert node["location"] == {"latitude": 11.870804, "longitude": 75.367665}
    assert node["formattedAddress"] == ""     # no addr:* tags on this one
    assert node["kind"] == "clinic"
    assert node["osm_url"] == "https://www.openstreetmap.org/node/5166902095"

    way = by_name["Kannur Gastro Care"]
    # This is what `out center` buys us for a way.
    assert way["location"] == {"latitude": 11.876, "longitude": 75.372}
    assert way["phone"] == "+91 497 1234567"
    assert way["opening_hours"] == "Mo-Sa 09:00-17:00"


def test_osrm_has_no_ratings_so_none_are_invented(sent_request):
    found = places.find_doctors("Gastroenterologist", 11.8745, 75.3704)

    # A 0 here would be scored, and read by a user, as "rated zero" - a worse
    # lie than admitting the data does not exist.
    for place in found:
        assert "rating" not in place
        assert "userRatingCount" not in place


def test_the_speciality_tag_or_the_name_can_mark_a_match(sent_request):
    found = places.find_doctors("Gastroenterologist", 11.8745, 75.3704)
    by_name = {place["displayName"]["text"]: place for place in found}

    # tagged healthcare:speciality=gastroenterology;hepatology
    assert by_name["Kannur Gastro Care"]["speciality_match"] is True
    assert by_name["Kannur Gastro Care"]["speciality"] == \
        "gastroenterology;hepatology"
    # Neither tagged nor named as one, so it must not claim to be.
    assert by_name["Railway Station Health Unit"]["speciality_match"] is False


def test_a_name_alone_is_enough_when_the_tag_is_missing(monkeypatch):
    # The common case in a small Indian town: no speciality tag anywhere, so
    # the facility's own name is the only evidence there is.
    element = {"type": "node", "id": 1, "lat": 11.87, "lon": 75.37,
               "tags": {"amenity": "clinic", "name": "Kannur Gastro Care"}}
    monkeypatch.setattr(places.requests, "post",
                        lambda url, **kwargs:
                        FakeResponse({"elements": [element]}))
    found = places.find_doctors("Gastroenterologist", 11.87, 75.37)
    assert found[0]["speciality_match"] is True


def test_an_unnamed_facility_says_so_instead_of_inventing_a_name(monkeypatch):
    element = {"type": "node", "id": 7, "lat": 11.87, "lon": 75.37,
               "tags": {"amenity": "clinic"}}
    monkeypatch.setattr(places.requests, "post",
                        lambda url, **kwargs:
                        FakeResponse({"elements": [element]}))
    found = places.find_doctors("Gastroenterologist", 11.87, 75.37)
    assert "Unnamed" in found[0]["displayName"]["text"]
    assert "clinic" in found[0]["displayName"]["text"]


def test_a_way_with_no_centre_is_dropped_not_crashed(monkeypatch):
    # app/ranking.py cannot score a place with no distance, so it must never
    # reach it: one unusable element must not cost the whole search.
    monkeypatch.setattr(places.requests, "post",
                        lambda url, **kwargs:
                        FakeResponse({"elements": [NO_CENTRE, NODE]}))
    found = places.find_doctors("Gastroenterologist", 11.87, 75.37)
    assert len(found) == 1
    assert found[0]["displayName"]["text"] == "Railway Station Health Unit"


def test_a_refusal_from_overpass_reaches_the_caller(monkeypatch):
    # 504 is Overpass saying "busy", 429 saying "slow down". Either way
    # app/main.py needs the exception, not a cheerful empty list - after the
    # one polite retry has also failed.
    monkeypatch.setattr(places, "RETRY_DELAY_S", 0)
    calls = []

    def always_busy(url, **kwargs):
        calls.append(url)
        return FakeResponse(status_code=504, text="gateway timeout")

    monkeypatch.setattr(places.requests, "post", always_busy)
    with pytest.raises(requests.HTTPError):
        places.find_doctors("Gastroenterologist", 11.8745, 75.3704)
    assert len(calls) == 2     # one retry, not a loop - Overpass usage policy


def test_one_transient_error_is_retried_and_then_succeeds(monkeypatch):
    # The exact failure behind the real 502s seen on 2026-10-06: a lone
    # gateway timeout from a shared server. The retry turns it into a
    # normal answer instead of an error page.
    monkeypatch.setattr(places, "RETRY_DELAY_S", 0)
    calls = {"n": 0}

    def flaky(url, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return FakeResponse(status_code=504, text="gateway timeout")
        return FakeResponse({"elements": [NODE]})

    monkeypatch.setattr(places.requests, "post", flaky)
    found = places.find_doctors("Gastroenterologist", 11.8745, 75.3704)
    assert len(found) == 1
    assert calls["n"] == 2


def test_a_permanent_client_error_is_not_pointlessly_retried(monkeypatch):
    # A 404 is our query's problem, not Overpass being busy: asking twice
    # would only double the wasted round-trip.
    monkeypatch.setattr(places, "RETRY_DELAY_S", 0)
    calls = []

    def wrong_url(url, **kwargs):
        calls.append(url)
        return FakeResponse(status_code=404, text="not found")

    monkeypatch.setattr(places.requests, "post", wrong_url)
    with pytest.raises(requests.HTTPError):
        places.find_doctors("Gastroenterologist", 11.8745, 75.3704)
    assert len(calls) == 1


def test_a_200_carrying_a_remark_is_not_reported_as_no_doctors(monkeypatch):
    # Overpass reports "runtime error: Query timed out" inside an HTTP 200. If
    # that were returned as an empty list, the user would be told their town
    # has no doctors - a wrong answer dressed up as a real one.
    payload = {"remark": "runtime error: Query timed out in 'recurse'",
               "elements": []}
    monkeypatch.setattr(places.requests, "post",
                        lambda url, **kwargs: FakeResponse(payload))
    with pytest.raises(RuntimeError, match="timed out"):
        places.find_doctors("Gastroenterologist", 11.8745, 75.3704)


def test_impossible_input_is_refused_before_any_request(monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("a request was sent with impossible input")

    monkeypatch.setattr(places.requests, "post", explode)
    for lat, lng, radius in ((91.0, 75.37, 5000), (11.87, 181.0, 5000),
                             (11.87, 75.37, 0), (11.87, 75.37, 999999)):
        with pytest.raises(ValueError):
            places.find_doctors("Gastroenterologist", lat, lng, radius)


def test_an_unknown_specialist_still_searches_but_verifies_nothing(monkeypatch):
    # app/mapping.py is the only source of specialist names, so this happens
    # only if someone passes a typo to --specialist. It has to degrade to
    # "nearby, none verified" rather than to an empty page.
    monkeypatch.setattr(places.requests, "post",
                        lambda url, **kwargs:
                        FakeResponse({"elements": [NODE]}))
    found = places.find_doctors("Wizard", 11.87, 75.37)
    assert len(found) == 1
    assert found[0]["speciality_match"] is False


def test_a_response_with_no_elements_is_an_empty_search_not_an_error(monkeypatch):
    # Empty is a legitimate answer - it is what rural coverage looks like - and
    # the smoke script reports it as a coverage fact rather than a failure.
    monkeypatch.setattr(places.requests, "post",
                        lambda url, **kwargs: FakeResponse({"elements": []}))
    assert places.find_doctors("Gastroenterologist", 11.87, 75.37) == []
