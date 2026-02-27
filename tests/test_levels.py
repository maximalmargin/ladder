"""Tests for ladder.levels — level configs, ordering, and navigation."""

from __future__ import annotations

import pytest

from ladder.levels import LEVEL_CONFIGS, LevelConfig, Pricing, get_config, next_level
from ladder.models import LadderLevel


class TestLevelConfigs:
    def test_all_six_levels_present(self):
        assert len(LEVEL_CONFIGS) == 6
        for level in LadderLevel:
            assert level in LEVEL_CONFIGS

    def test_intern_config(self):
        cfg = LEVEL_CONFIGS[LadderLevel.intern]
        assert cfg.model_id == "claude-haiku-4-5-20251001"
        assert cfg.max_output_tokens == 2048
        assert cfg.pricing.input_per_mtok == 1.00
        assert cfg.pricing.output_per_mtok == 5.00

    def test_junior_config(self):
        cfg = LEVEL_CONFIGS[LadderLevel.junior]
        assert cfg.model_id == "claude-haiku-4-5-20251001"
        assert cfg.max_output_tokens == 4096

    def test_mid_config(self):
        cfg = LEVEL_CONFIGS[LadderLevel.mid]
        assert cfg.model_id == "claude-sonnet-4-5-20250929"
        assert cfg.max_output_tokens == 8192
        assert cfg.pricing.input_per_mtok == 3.00
        assert cfg.pricing.output_per_mtok == 15.00

    def test_senior_config(self):
        cfg = LEVEL_CONFIGS[LadderLevel.senior]
        assert cfg.model_id == "claude-sonnet-4-5-20250929"
        assert cfg.max_output_tokens == 16384

    def test_staff_config(self):
        cfg = LEVEL_CONFIGS[LadderLevel.staff]
        assert cfg.model_id == "claude-opus-4-6"
        assert cfg.max_output_tokens == 32768
        assert cfg.pricing.input_per_mtok == 5.00
        assert cfg.pricing.output_per_mtok == 25.00

    def test_principal_config(self):
        cfg = LEVEL_CONFIGS[LadderLevel.principal]
        assert cfg.model_id == "claude-opus-4-6"
        assert cfg.max_output_tokens == 65536

    def test_model_tiers(self):
        """Haiku for intern/junior, Sonnet for mid/senior, Opus for staff/principal."""
        haiku_levels = [LadderLevel.intern, LadderLevel.junior]
        sonnet_levels = [LadderLevel.mid, LadderLevel.senior]
        opus_levels = [LadderLevel.staff, LadderLevel.principal]

        for level in haiku_levels:
            assert "haiku" in LEVEL_CONFIGS[level].model_id
        for level in sonnet_levels:
            assert "sonnet" in LEVEL_CONFIGS[level].model_id
        for level in opus_levels:
            assert "opus" in LEVEL_CONFIGS[level].model_id

    def test_max_tokens_increase_with_level(self):
        """Higher levels should have equal or more output tokens."""
        levels = list(LadderLevel)
        for i in range(len(levels) - 1):
            curr = LEVEL_CONFIGS[levels[i]].max_output_tokens
            next_ = LEVEL_CONFIGS[levels[i + 1]].max_output_tokens
            assert next_ >= curr, f"{levels[i+1]} should have >= tokens than {levels[i]}"

    def test_each_config_has_description(self):
        for level, cfg in LEVEL_CONFIGS.items():
            assert cfg.description, f"{level} config missing description"

    def test_configs_are_frozen(self):
        cfg = LEVEL_CONFIGS[LadderLevel.intern]
        with pytest.raises(AttributeError):
            cfg.model_id = "changed"


class TestGetConfig:
    def test_each_level(self):
        for level in LadderLevel:
            cfg = get_config(level)
            assert isinstance(cfg, LevelConfig)
            assert cfg.level == level

    def test_returns_same_object(self):
        cfg1 = get_config(LadderLevel.mid)
        cfg2 = get_config(LadderLevel.mid)
        assert cfg1 is cfg2


class TestNextLevel:
    def test_intern_to_junior(self):
        assert next_level(LadderLevel.intern) == LadderLevel.junior

    def test_junior_to_mid(self):
        assert next_level(LadderLevel.junior) == LadderLevel.mid

    def test_mid_to_senior(self):
        assert next_level(LadderLevel.mid) == LadderLevel.senior

    def test_senior_to_staff(self):
        assert next_level(LadderLevel.senior) == LadderLevel.staff

    def test_staff_to_principal(self):
        assert next_level(LadderLevel.staff) == LadderLevel.principal

    def test_principal_returns_none(self):
        assert next_level(LadderLevel.principal) is None

    def test_full_chain(self):
        """Walk the full chain from intern to principal."""
        level = LadderLevel.intern
        visited = [level]
        while True:
            nxt = next_level(level)
            if nxt is None:
                break
            visited.append(nxt)
            level = nxt
        assert visited == list(LadderLevel)
