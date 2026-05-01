from pathlib import Path

from middle_passage.voyages.loader import load_voyages


def test_load_voyages_flexible_csv(tmp_path: Path):
    source = tmp_path / "voyages.csv"
    source.write_text(
        "voyage_id,ship_name,port_embark_lat,port_embark_lon,slaves_embarked,slaves_died_middle_passage,jettison_flag\n"
        "v1,Example,1.5,-30.5,100,12,yes\n",
        encoding="utf-8",
    )

    voyages = load_voyages(source)

    assert len(voyages) == 1
    assert voyages[0].voyage_id == "v1"
    assert voyages[0].mortality_rate == 0.12
    assert voyages[0].jettison_flag is True
    assert voyages[0].embark is not None

