from sanmiao.date_authority import list_date_authority


def test_list_date_authority_has_song_dynasty():
    data = list_date_authority(civ=["c"])
    dyn_ids = {entry["dynId"] for entry in data["dynasties"]}
    assert 119 in dyn_ids

    song_eras = [e for e in data["eras"] if e["dynId"] == 119]
    assert len(song_eras) > 0
    assert any(e["label"] == "建隆" for e in song_eras)

    song_rulers = [r for r in data["rulers"] if r["dynId"] == 119]
    assert len(song_rulers) > 0
