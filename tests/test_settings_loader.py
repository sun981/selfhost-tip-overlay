"""
Settings loader invariants: shipped defaults load alone, user/settings.json
shallow-overrides per top-level key, absent files never crash.
"""
from __future__ import annotations

import json

from app import settings_loader


def test_defaults_load_without_user_file(tmp_path, monkeypatch):
    default = tmp_path / "settings.json"
    default.write_text(json.dumps({"banned_words": [], "message_max_length": 200}))
    monkeypatch.setattr(settings_loader, "DEFAULT_SETTINGS_PATH", default)
    monkeypatch.setattr(settings_loader, "USER_SETTINGS_PATH", tmp_path / "missing.json")

    settings = settings_loader.load_settings()
    assert settings["message_max_length"] == 200


def test_user_file_overrides_per_top_level_key(tmp_path, monkeypatch):
    default = tmp_path / "settings.json"
    default.write_text(json.dumps({"banned_words": [], "message_max_length": 200}))
    user = tmp_path / "user-settings.json"
    user.write_text(json.dumps({"banned_words": ["spam"]}))
    monkeypatch.setattr(settings_loader, "DEFAULT_SETTINGS_PATH", default)
    monkeypatch.setattr(settings_loader, "USER_SETTINGS_PATH", user)

    settings = settings_loader.load_settings()
    assert settings["banned_words"] == ["spam"]       # user wins
    assert settings["message_max_length"] == 200      # untouched keys keep defaults


def test_no_files_returns_empty_dict(tmp_path, monkeypatch):
    monkeypatch.setattr(settings_loader, "DEFAULT_SETTINGS_PATH", tmp_path / "a.json")
    monkeypatch.setattr(settings_loader, "USER_SETTINGS_PATH", tmp_path / "b.json")
    assert settings_loader.load_settings() == {}
