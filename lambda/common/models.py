"""Data models for the rewards program system."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, validator


class Tier(str, Enum):
    """Membership tier levels."""
    GREEN = "Green"
    GOLD = "Gold"
    RESERVE = "Reserve"


class TransactionType(str, Enum):
    """Types of transactions in the system."""
    PURCHASE = "purchase"
    REDEMPTION = "redemption"
    EXPIRATION = "expiration"
    TIER_CHANGE = "tier_change"


class MemberProfile(BaseModel):
    """Member profile data model."""
    membership_id: str
    email: str
    name: str
    phone: str
    tier: Tier = Tier.GREEN
    star_balance: int = 0
    annual_star_count: int = 0
    enrollment_date: datetime
    last_qualifying_activity: Optional[datetime] = None
    tier_since: datetime
    next_tier_evaluation: datetime


class Transaction(BaseModel):
    """Transaction record data model."""
    transaction_id: str
    membership_id: str
    type: TransactionType
    timestamp: datetime
    stars_earned: Optional[int] = None
    stars_redeemed: Optional[int] = None
    purchase_amount: Optional[Decimal] = None
    description: Optional[str] = None


class StarLedgerEntry(BaseModel):
    """Star ledger entry for tracking expiration (Green tier only)."""
    membership_id: str
    earned_date: datetime
    star_count: int
    expiration_date: Optional[datetime] = None
    batch_id: str


class SignupEventData(BaseModel):
    """Data payload for signup events."""
    email: str
    name: str
    phone: str


class PurchaseEventData(BaseModel):
    """Data payload for purchase events."""
    membership_id: str
    amount: Decimal = Field(gt=0)
    double_star_day: bool = False
    personal_cup: bool = False

    @validator('amount')
    def validate_amount(cls, v: Decimal) -> Decimal:
        """Ensure amount is positive."""
        if v <= 0:
            raise ValueError("Purchase amount must be positive")
        return v


class RedemptionEventData(BaseModel):
    """Data payload for redemption events."""
    membership_id: str
    stars_to_redeem: int = Field(ge=60)  # Only use ge (greater than or equal to)
    item_description: str

    @validator('stars_to_redeem')
    def validate_stars(cls, v: int) -> int:
        """Ensure redemption is at least 60 stars."""
        if v < 60:
            raise ValueError("Minimum redemption is 60 stars")
        return v


class EventMessage(BaseModel):
    """Base event message structure."""
    event_type: str
    transaction_id: str
    timestamp: datetime
    data: dict


class MemberResponse(BaseModel):
    """API response for member queries."""
    membership_id: str
    tier: Tier
    star_balance: int
    annual_star_count: int
    enrollment_date: datetime
    last_activity: Optional[datetime] = None
    tier_since: datetime


class TransactionHistoryResponse(BaseModel):
    """API response for transaction history queries."""
    transactions: list[Transaction]
    next_token: Optional[str] = None


class ErrorResponse(BaseModel):
    """Standard error response format."""
    error: dict = Field(
        description="Error details including code, message, and additional context"
    )
