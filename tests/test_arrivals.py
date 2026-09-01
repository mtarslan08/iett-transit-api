from iett_tracker.arrivals import IettArrivalProvider


def test_arrival_parser_extracts_eta_and_time():
    html = '<div id="departure"><div class="line-item">Kartal (14:20) 7 dk</div></div>'
    result = IettArrivalProvider()._parse(html, "KM34")
    assert result["arrivals"][0].eta_minutes == 7
    assert result["arrivals"][0].departure_time == "14:20"
