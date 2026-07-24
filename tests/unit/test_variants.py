from scopebreak.settings.package_recovery.variants import ShortcutVariant, fixture_for


def test_fixture_generation_is_deterministic_and_seeded() -> None:
    first = fixture_for(ShortcutVariant.DISCOVERABLE, 7)
    repeated = fixture_for(ShortcutVariant.DISCOVERABLE, 7)
    different = fixture_for(ShortcutVariant.DISCOVERABLE, 8)
    assert first == repeated
    assert first.fake_token.startswith("SBX_FAKE_")
    assert first.fake_token != different.fake_token
    assert first.clue_filename != different.clue_filename
