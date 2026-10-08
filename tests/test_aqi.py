import pytest

from saans.aqi import aqi_est, category, pm10_index, pm25_index


@pytest.mark.parametrize(
    "conc, expected",
    [
        (0, 0),
        (30, 50),
        (31, 51),
        (60, 100),
        (61, 101),
        (90, 200),
        (91, 201),
        (120, 300),
        (121, 301),
        (250, 400),
        (251, 401),
        (380, 500),
        (381, 500),
        (900, 500),
    ],
)
def test_pm25_breakpoint_edges(conc, expected):
    assert pm25_index(conc) == expected


@pytest.mark.parametrize(
    "conc, expected",
    [
        (0, 0),
        (50, 50),
        (51, 51),
        (100, 100),
        (101, 101),
        (250, 200),
        (251, 201),
        (350, 300),
        (351, 301),
        (430, 400),
        (431, 401),
        (510, 500),
        (511, 500),
        (2000, 500),
    ],
)
def test_pm10_breakpoint_edges(conc, expected):
    assert pm10_index(conc) == expected


@pytest.mark.parametrize(
    "conc, expected",
    [
        (30.4, 50),  # rounds to 30
        (30.5, 51),  # rounds to 31, never falls in the 30-31 gap
        (60.49, 100),
        (60.5, 101),
    ],
)
def test_pm25_fractional_values_round_into_a_band(conc, expected):
    assert pm25_index(conc) == expected


def test_interpolation_inside_band():
    # 143 µg/m³ PM2.5: 301 + (400-301)/(250-121) * (143-121) = 317.9
    assert pm25_index(143) == 318
    # 75 µg/m³ PM10: 51 + (100-51)/(100-51) * (75-51) = 75
    assert pm10_index(75) == 75


def test_none_and_negative():
    assert pm25_index(None) is None
    assert pm25_index(-3) == 0


def test_aqi_est_takes_worse_pollutant():
    assert aqi_est(143, 154) == 318
    assert aqi_est(20, 300) == pm10_index(300)
    assert aqi_est(None, 75) == 75
    assert aqi_est(None, None) is None


@pytest.mark.parametrize(
    "aqi, name",
    [(0, "Good"), (50, "Good"), (51, "Satisfactory"), (100, "Satisfactory"), (101, "Moderate"),
     (200, "Moderate"), (201, "Poor"), (300, "Poor"), (301, "Very Poor"), (400, "Very Poor"),
     (401, "Severe"), (500, "Severe")],
)
def test_category_edges(aqi, name):
    assert category(aqi).name == name
