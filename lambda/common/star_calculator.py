"""Star calculation logic for the rewards program.

This module handles the calculation of stars earned from purchases based on:
- Member tier (Green: 1.0x, Gold: 1.2x, Reserve: 1.7x)
- Double star day multiplier (2.0x)
- Personal cup multiplier (2.0x)
- Combined multipliers when multiple apply
"""

from decimal import Decimal
from typing import Union
from common.models import Tier


# Tier-based star earning rates (stars per dollar)
TIER_RATES = {
    Tier.GREEN: Decimal("1.0"),
    Tier.GOLD: Decimal("1.2"),
    Tier.RESERVE: Decimal("1.7"),
}

# Multipliers for special conditions
DOUBLE_STAR_DAY_MULTIPLIER = Decimal("2.0")
PERSONAL_CUP_MULTIPLIER = Decimal("2.0")


def calculate_stars(
    purchase_amount: Union[Decimal, float],
    tier: Tier,
    double_star_day: bool = False,
    personal_cup: bool = False,
) -> int:
    """
    Calculate stars earned from a purchase.
    
    The calculation follows this formula:
    stars = purchase_amount × tier_rate × double_star_multiplier × personal_cup_multiplier
    
    Where:
    - tier_rate is 1.0 (Green), 1.2 (Gold), or 1.7 (Reserve)
    - double_star_multiplier is 2.0 if double_star_day is True, else 1.0
    - personal_cup_multiplier is 2.0 if personal_cup is True, else 1.0
    
    Args:
        purchase_amount: Purchase amount in dollars
        tier: Member's current tier
        double_star_day: Whether the purchase is on a double star day
        personal_cup: Whether the member used a personal cup
        
    Returns:
        Number of stars earned (rounded down to nearest integer)
        
    Examples:
        >>> calculate_stars(Decimal("10.00"), Tier.GREEN)
        10
        >>> calculate_stars(Decimal("10.00"), Tier.GOLD)
        12
        >>> calculate_stars(Decimal("10.00"), Tier.RESERVE)
        17
        >>> calculate_stars(Decimal("10.00"), Tier.GREEN, double_star_day=True)
        20
        >>> calculate_stars(Decimal("10.00"), Tier.GREEN, personal_cup=True)
        20
        >>> calculate_stars(Decimal("10.00"), Tier.GOLD, double_star_day=True, personal_cup=True)
        48
    """
    # Convert float to Decimal if needed
    if isinstance(purchase_amount, float):
        purchase_amount = Decimal(str(purchase_amount))
    
    # Get base tier rate
    tier_rate = TIER_RATES[tier]
    
    # Calculate base stars from tier rate
    stars = purchase_amount * tier_rate
    
    # Apply double star day multiplier if applicable
    if double_star_day:
        stars *= DOUBLE_STAR_DAY_MULTIPLIER
    
    # Apply personal cup multiplier if applicable
    if personal_cup:
        stars *= PERSONAL_CUP_MULTIPLIER
    
    # Round down to nearest integer
    return int(stars)


def get_tier_rate(tier: Tier) -> Decimal:
    """
    Get the star earning rate for a given tier.
    
    Args:
        tier: Member's tier
        
    Returns:
        Star earning rate (stars per dollar)
        
    Examples:
        >>> get_tier_rate(Tier.GREEN)
        Decimal('1.0')
        >>> get_tier_rate(Tier.GOLD)
        Decimal('1.2')
        >>> get_tier_rate(Tier.RESERVE)
        Decimal('1.7')
    """
    return TIER_RATES[tier]


def calculate_effective_multiplier(
    double_star_day: bool = False,
    personal_cup: bool = False,
) -> Decimal:
    """
    Calculate the effective multiplier from special conditions.
    
    When both double star day and personal cup apply, the multipliers
    are combined multiplicatively (2.0 × 2.0 = 4.0).
    
    Args:
        double_star_day: Whether the purchase is on a double star day
        personal_cup: Whether the member used a personal cup
        
    Returns:
        Combined multiplier
        
    Examples:
        >>> calculate_effective_multiplier()
        Decimal('1.0')
        >>> calculate_effective_multiplier(double_star_day=True)
        Decimal('2.0')
        >>> calculate_effective_multiplier(personal_cup=True)
        Decimal('2.0')
        >>> calculate_effective_multiplier(double_star_day=True, personal_cup=True)
        Decimal('4.0')
    """
    multiplier = Decimal("1.0")
    
    if double_star_day:
        multiplier *= DOUBLE_STAR_DAY_MULTIPLIER
    
    if personal_cup:
        multiplier *= PERSONAL_CUP_MULTIPLIER
    
    return multiplier
