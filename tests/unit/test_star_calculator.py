"""Unit tests for star calculation logic."""

import pytest
from decimal import Decimal
from common.models import Tier
from common.star_calculator import (
    calculate_stars,
    get_tier_rate,
    calculate_effective_multiplier,
    TIER_RATES,
    DOUBLE_STAR_DAY_MULTIPLIER,
    PERSONAL_CUP_MULTIPLIER,
)


class TestTierRates:
    """Test tier-based star earning rates."""
    
    def test_green_tier_rate(self):
        """Green tier should earn 1.0 stars per dollar."""
        assert get_tier_rate(Tier.GREEN) == Decimal("1.0")
    
    def test_gold_tier_rate(self):
        """Gold tier should earn 1.2 stars per dollar."""
        assert get_tier_rate(Tier.GOLD) == Decimal("1.2")
    
    def test_reserve_tier_rate(self):
        """Reserve tier should earn 1.7 stars per dollar."""
        assert get_tier_rate(Tier.RESERVE) == Decimal("1.7")
    
    def test_tier_rates_constant(self):
        """Verify TIER_RATES constant has correct values."""
        assert TIER_RATES[Tier.GREEN] == Decimal("1.0")
        assert TIER_RATES[Tier.GOLD] == Decimal("1.2")
        assert TIER_RATES[Tier.RESERVE] == Decimal("1.7")


class TestBasicStarCalculation:
    """Test basic star calculation without multipliers."""
    
    def test_green_tier_basic_calculation(self):
        """Green tier: $10 should earn 10 stars."""
        stars = calculate_stars(Decimal("10.00"), Tier.GREEN)
        assert stars == 10
    
    def test_gold_tier_basic_calculation(self):
        """Gold tier: $10 should earn 12 stars."""
        stars = calculate_stars(Decimal("10.00"), Tier.GOLD)
        assert stars == 12
    
    def test_reserve_tier_basic_calculation(self):
        """Reserve tier: $10 should earn 17 stars."""
        stars = calculate_stars(Decimal("10.00"), Tier.RESERVE)
        assert stars == 17
    
    def test_fractional_amount_green(self):
        """Green tier: $5.50 should earn 5 stars (rounded down)."""
        stars = calculate_stars(Decimal("5.50"), Tier.GREEN)
        assert stars == 5
    
    def test_fractional_amount_gold(self):
        """Gold tier: $5.50 should earn 6 stars (5.5 × 1.2 = 6.6, rounded down)."""
        stars = calculate_stars(Decimal("5.50"), Tier.GOLD)
        assert stars == 6
    
    def test_fractional_amount_reserve(self):
        """Reserve tier: $5.50 should earn 9 stars (5.5 × 1.7 = 9.35, rounded down)."""
        stars = calculate_stars(Decimal("5.50"), Tier.RESERVE)
        assert stars == 9
    
    def test_small_purchase_green(self):
        """Green tier: $0.50 should earn 0 stars (rounded down)."""
        stars = calculate_stars(Decimal("0.50"), Tier.GREEN)
        assert stars == 0
    
    def test_large_purchase_reserve(self):
        """Reserve tier: $100 should earn 170 stars."""
        stars = calculate_stars(Decimal("100.00"), Tier.RESERVE)
        assert stars == 170
    
    def test_float_input_conversion(self):
        """Float inputs should be converted to Decimal correctly."""
        stars = calculate_stars(10.0, Tier.GREEN)
        assert stars == 10


class TestDoubleStarDayMultiplier:
    """Test double star day multiplier (2.0x)."""
    
    def test_green_double_star_day(self):
        """Green tier with double star day: $10 should earn 20 stars."""
        stars = calculate_stars(Decimal("10.00"), Tier.GREEN, double_star_day=True)
        assert stars == 20
    
    def test_gold_double_star_day(self):
        """Gold tier with double star day: $10 should earn 24 stars."""
        stars = calculate_stars(Decimal("10.00"), Tier.GOLD, double_star_day=True)
        assert stars == 24
    
    def test_reserve_double_star_day(self):
        """Reserve tier with double star day: $10 should earn 34 stars."""
        stars = calculate_stars(Decimal("10.00"), Tier.RESERVE, double_star_day=True)
        assert stars == 34
    
    def test_double_star_day_with_fractional(self):
        """Double star day with fractional amount should round down correctly."""
        stars = calculate_stars(Decimal("5.25"), Tier.GREEN, double_star_day=True)
        # 5.25 × 1.0 × 2.0 = 10.5, rounded down to 10
        assert stars == 10
    
    def test_double_star_day_false(self):
        """Explicitly setting double_star_day=False should not apply multiplier."""
        stars = calculate_stars(Decimal("10.00"), Tier.GREEN, double_star_day=False)
        assert stars == 10


class TestPersonalCupMultiplier:
    """Test personal cup multiplier (2.0x)."""
    
    def test_green_personal_cup(self):
        """Green tier with personal cup: $10 should earn 20 stars."""
        stars = calculate_stars(Decimal("10.00"), Tier.GREEN, personal_cup=True)
        assert stars == 20
    
    def test_gold_personal_cup(self):
        """Gold tier with personal cup: $10 should earn 24 stars."""
        stars = calculate_stars(Decimal("10.00"), Tier.GOLD, personal_cup=True)
        assert stars == 24
    
    def test_reserve_personal_cup(self):
        """Reserve tier with personal cup: $10 should earn 34 stars."""
        stars = calculate_stars(Decimal("10.00"), Tier.RESERVE, personal_cup=True)
        assert stars == 34
    
    def test_personal_cup_with_fractional(self):
        """Personal cup with fractional amount should round down correctly."""
        stars = calculate_stars(Decimal("5.75"), Tier.GREEN, personal_cup=True)
        # 5.75 × 1.0 × 2.0 = 11.5, rounded down to 11
        assert stars == 11
    
    def test_personal_cup_false(self):
        """Explicitly setting personal_cup=False should not apply multiplier."""
        stars = calculate_stars(Decimal("10.00"), Tier.GREEN, personal_cup=False)
        assert stars == 10


class TestCombinedMultipliers:
    """Test combined double star day and personal cup multipliers."""
    
    def test_green_both_multipliers(self):
        """Green tier with both multipliers: $10 should earn 40 stars (2.0 × 2.0 = 4.0x)."""
        stars = calculate_stars(
            Decimal("10.00"), 
            Tier.GREEN, 
            double_star_day=True, 
            personal_cup=True
        )
        assert stars == 40
    
    def test_gold_both_multipliers(self):
        """Gold tier with both multipliers: $10 should earn 48 stars (1.2 × 4.0 = 4.8x)."""
        stars = calculate_stars(
            Decimal("10.00"), 
            Tier.GOLD, 
            double_star_day=True, 
            personal_cup=True
        )
        assert stars == 48
    
    def test_reserve_both_multipliers(self):
        """Reserve tier with both multipliers: $10 should earn 68 stars (1.7 × 4.0 = 6.8x)."""
        stars = calculate_stars(
            Decimal("10.00"), 
            Tier.RESERVE, 
            double_star_day=True, 
            personal_cup=True
        )
        assert stars == 68
    
    def test_combined_multipliers_with_fractional(self):
        """Combined multipliers with fractional amount should round down correctly."""
        stars = calculate_stars(
            Decimal("7.30"), 
            Tier.GOLD, 
            double_star_day=True, 
            personal_cup=True
        )
        # 7.30 × 1.2 × 2.0 × 2.0 = 35.04, rounded down to 35
        assert stars == 35
    
    def test_combined_multipliers_edge_case(self):
        """Test edge case where combined multipliers create fractional stars."""
        stars = calculate_stars(
            Decimal("3.33"), 
            Tier.RESERVE, 
            double_star_day=True, 
            personal_cup=True
        )
        # 3.33 × 1.7 × 2.0 × 2.0 = 22.644, rounded down to 22
        assert stars == 22


class TestEffectiveMultiplier:
    """Test effective multiplier calculation."""
    
    def test_no_multipliers(self):
        """No multipliers should return 1.0."""
        multiplier = calculate_effective_multiplier()
        assert multiplier == Decimal("1.0")
    
    def test_double_star_day_only(self):
        """Double star day only should return 2.0."""
        multiplier = calculate_effective_multiplier(double_star_day=True)
        assert multiplier == Decimal("2.0")
    
    def test_personal_cup_only(self):
        """Personal cup only should return 2.0."""
        multiplier = calculate_effective_multiplier(personal_cup=True)
        assert multiplier == Decimal("2.0")
    
    def test_both_multipliers(self):
        """Both multipliers should return 4.0 (2.0 × 2.0)."""
        multiplier = calculate_effective_multiplier(
            double_star_day=True, 
            personal_cup=True
        )
        assert multiplier == Decimal("4.0")
    
    def test_explicit_false_values(self):
        """Explicitly setting both to False should return 1.0."""
        multiplier = calculate_effective_multiplier(
            double_star_day=False, 
            personal_cup=False
        )
        assert multiplier == Decimal("1.0")


class TestEdgeCases:
    """Test edge cases and boundary conditions."""
    
    def test_zero_purchase_amount(self):
        """Zero purchase amount should earn 0 stars."""
        stars = calculate_stars(Decimal("0.00"), Tier.GREEN)
        assert stars == 0
    
    def test_very_small_amount(self):
        """Very small amount should round down to 0 stars."""
        stars = calculate_stars(Decimal("0.01"), Tier.GREEN)
        assert stars == 0
    
    def test_amount_just_under_one_star(self):
        """Amount just under earning 1 star should round down to 0."""
        stars = calculate_stars(Decimal("0.99"), Tier.GREEN)
        assert stars == 0
    
    def test_amount_exactly_one_star(self):
        """Amount exactly earning 1 star should return 1."""
        stars = calculate_stars(Decimal("1.00"), Tier.GREEN)
        assert stars == 1
    
    def test_large_purchase_amount(self):
        """Large purchase amount should calculate correctly."""
        stars = calculate_stars(Decimal("1000.00"), Tier.RESERVE)
        assert stars == 1700
    
    def test_large_purchase_with_multipliers(self):
        """Large purchase with all multipliers should calculate correctly."""
        stars = calculate_stars(
            Decimal("500.00"), 
            Tier.RESERVE, 
            double_star_day=True, 
            personal_cup=True
        )
        # 500 × 1.7 × 2.0 × 2.0 = 3400
        assert stars == 3400
    
    def test_precision_with_many_decimals(self):
        """Amount with many decimal places should handle precision correctly."""
        stars = calculate_stars(Decimal("12.3456789"), Tier.GOLD)
        # 12.3456789 × 1.2 = 14.81481468, rounded down to 14
        assert stars == 14


class TestMultiplierConstants:
    """Test that multiplier constants have correct values."""
    
    def test_double_star_day_multiplier_value(self):
        """Double star day multiplier should be 2.0."""
        assert DOUBLE_STAR_DAY_MULTIPLIER == Decimal("2.0")
    
    def test_personal_cup_multiplier_value(self):
        """Personal cup multiplier should be 2.0."""
        assert PERSONAL_CUP_MULTIPLIER == Decimal("2.0")


# Parametrized tests for comprehensive coverage
@pytest.mark.parametrize("tier,expected_rate", [
    (Tier.GREEN, Decimal("1.0")),
    (Tier.GOLD, Decimal("1.2")),
    (Tier.RESERVE, Decimal("1.7")),
])
def test_tier_rates_parametrized(tier, expected_rate):
    """Parametrized test for all tier rates."""
    assert get_tier_rate(tier) == expected_rate


@pytest.mark.parametrize("amount,tier,expected", [
    (Decimal("10.00"), Tier.GREEN, 10),
    (Decimal("10.00"), Tier.GOLD, 12),
    (Decimal("10.00"), Tier.RESERVE, 17),
    (Decimal("25.00"), Tier.GREEN, 25),
    (Decimal("25.00"), Tier.GOLD, 30),
    (Decimal("25.00"), Tier.RESERVE, 42),
    (Decimal("100.00"), Tier.GREEN, 100),
    (Decimal("100.00"), Tier.GOLD, 120),
    (Decimal("100.00"), Tier.RESERVE, 170),
])
def test_basic_calculations_parametrized(amount, tier, expected):
    """Parametrized test for basic star calculations across tiers."""
    assert calculate_stars(amount, tier) == expected


@pytest.mark.parametrize("amount,tier,double_star,personal_cup,expected", [
    # Green tier combinations
    (Decimal("10.00"), Tier.GREEN, False, False, 10),
    (Decimal("10.00"), Tier.GREEN, True, False, 20),
    (Decimal("10.00"), Tier.GREEN, False, True, 20),
    (Decimal("10.00"), Tier.GREEN, True, True, 40),
    # Gold tier combinations
    (Decimal("10.00"), Tier.GOLD, False, False, 12),
    (Decimal("10.00"), Tier.GOLD, True, False, 24),
    (Decimal("10.00"), Tier.GOLD, False, True, 24),
    (Decimal("10.00"), Tier.GOLD, True, True, 48),
    # Reserve tier combinations
    (Decimal("10.00"), Tier.RESERVE, False, False, 17),
    (Decimal("10.00"), Tier.RESERVE, True, False, 34),
    (Decimal("10.00"), Tier.RESERVE, False, True, 34),
    (Decimal("10.00"), Tier.RESERVE, True, True, 68),
])
def test_multiplier_combinations_parametrized(amount, tier, double_star, personal_cup, expected):
    """Parametrized test for all multiplier combinations across tiers."""
    stars = calculate_stars(amount, tier, double_star, personal_cup)
    assert stars == expected
