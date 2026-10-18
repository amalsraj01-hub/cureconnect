from app.ranking import bayesian_rating, distance_km


def test_few_reviews_pulled_toward_average():
    assert bayesian_rating(5.0, 1) < bayesian_rating(4.6, 200)


def test_distance_zero():
    assert distance_km(11.87, 75.37, 11.87, 75.37) == 0


def test_a_place_without_ratings_is_not_scored_as_if_rated_zero():
    # OpenStreetMap has no ratings. Pushing a 0 through the Bayesian formula
    # would drag every listing to the global average and quietly pretend a
    # rating existed, so unrated places are scored on distance instead.
    from app.ranking import rank_places
    unrated = {"id": "osm:node/1", "displayName": {"text": "Kannur Clinic"},
               "location": {"latitude": 11.87, "longitude": 75.37}}
    scored = rank_places([unrated], 11.87, 75.37)[0]

    assert scored["rating"] is None     # "not rated", not "rated zero"
    assert scored["reviews"] == 0
    assert scored["score"] > 0.4        # at distance ~0, distance is all of it
    # There is nothing to be limited about when there are no reviews at all.
    assert scored["limited_reviews"] is False


def test_the_right_specialist_outranks_a_slightly_nearer_stranger():
    from app.ranking import rank_places
    nearer = {"id": "nearer", "displayName": {"text": "Next-door clinic"},
              "location": {"latitude": 11.8702, "longitude": 75.3704},
              "speciality_match": False}
    # About 2 km north, but tagged as the speciality that was asked for.
    farther = {"id": "farther", "displayName": {"text": "Gastro clinic"},
               "location": {"latitude": 11.8925, "longitude": 75.3704},
               "speciality_match": True,
               "healthcare:speciality": "gastroenterology"}
    ranked = rank_places([nearer, farther], 11.8745, 75.3704)

    assert ranked[0]["id"] == "farther"
    assert ranked[0]["speciality_match"] is True


def test_a_rated_place_still_uses_the_original_formula():
    # Kept for whenever a source with ratings is used again: the unrated path
    # must not have quietly changed the rated one.
    from app.ranking import rank_places
    rated = {"id": "google", "displayName": {"text": "Some Clinic"},
             "location": {"latitude": 11.87, "longitude": 75.37},
             "rating": 4.6, "userRatingCount": 200}
    scored = rank_places([rated], 11.87, 75.37)[0]

    assert scored["rating"] == 4.6
    assert scored["reviews"] == 200
    assert scored["limited_reviews"] is False
    # 0.55 * rating_norm + 0.25 * 1 + 0.20 * 1, at distance zero.
    expected = 0.55 * bayesian_rating(4.6, 200) / 5 + 0.25 + 0.20
    assert abs(scored["score"] - expected) < 0.001


def test_a_place_with_no_coordinates_is_skipped_not_crashed():
    # This rule lives in app/ranking.py, not app/places.py: a response field
    # can simply be missing, and a place with no location cannot be scored.
    from app.ranking import rank_places
    places_with_gap = [{"location": {"latitude": 11.87, "longitude": 75.37}},
                       {"id": "no-coordinates"}]
    assert len(rank_places(places_with_gap, 11.8745, 75.3704)) == 1


def test_scored_place_carries_coordinates_for_the_map():
    # frontend/index.html draws a marker per doctor (Stage 8), so the ranked
    # dict has to pass the place's own coordinates through untouched.
    from app.ranking import rank_places
    place = {"id": "osm:node/2", "displayName": {"text": "Kannur Clinic"},
             "location": {"latitude": 11.8745, "longitude": 75.3704}}
    scored = rank_places([place], 11.8745, 75.3704)[0]
    assert scored["lat"] == 11.8745
    assert scored["lng"] == 75.3704
