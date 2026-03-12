"""Unit tests for event validation module."""

import pytest
from decimal import Decimal
from datetime import datetime
from common.validation import (
    ValidationException,
    ErrorCode,
    validate_event_message,
    validate_signup_data,
    validate_purchase_data,
    validate_redemption_data,
    validate_membership_id,
    create_error_response,
)


class TestEventMessageValidation:
    """Tests for base event message validation."""

    def test_valid_event_message(self):
        """Test validation of a valid event message."""
        event = {
            "event_type": "rewards.member.signup",
            "transaction_id": "test-txn-123",
            "timestamp": datetime.utcnow().isoformat(),
            "data": {"email": "test@example.com", "name": "Test User", "phone": "1234567890"}
        }
        
        result = validate_event_message(event)
        assert result.event_type == "rewards.member.signup"
        assert result.transaction_id == "test-txn-123"

    def test_missing_required_fields(self):
        """Test validation fails when required fields are missing."""
        event = {
            "event_type": "rewards.member.signup",
            "data": {}
        }
        
        with pytest.raises(ValidationException) as exc_info:
            validate_event_message(event)
        
        assert exc_info.value.code == ErrorCode.MISSING_REQUIRED_FIELDS
        assert "transaction_id" in exc_info.value.details["missing_fields"]
        assert "timestamp" in exc_info.value.details["missing_fields"]

    def test_invalid_data_types(self):
        """Test validation fails when data types are invalid."""
        event = {
            "event_type": "rewards.member.signup",
            "transaction_id": 12345,  # Should be string
            "timestamp": "not-a-valid-timestamp",
            "data": {}
        }
        
        with pytest.raises(ValidationException) as exc_info:
            validate_event_message(event)
        
        assert exc_info.value.code in [ErrorCode.INVALID_DATA_TYPE, ErrorCode.MISSING_REQUIRED_FIELDS]


class TestSignupDataValidation:
    """Tests for signup event data validation."""

    def test_valid_signup_data(self):
        """Test validation of valid signup data."""
        data = {
            "email": "test@example.com",
            "name": "Test User",
            "phone": "1234567890"
        }
        
        result = validate_signup_data(data)
        assert result.email == "test@example.com"
        assert result.name == "Test User"
        assert result.phone == "1234567890"

    def test_missing_email(self):
        """Test validation fails when email is missing."""
        data = {
            "name": "Test User",
            "phone": "1234567890"
        }
        
        with pytest.raises(ValidationException) as exc_info:
            validate_signup_data(data)
        
        assert exc_info.value.code == ErrorCode.MISSING_REQUIRED_FIELDS
        assert "email" in exc_info.value.details["missing_fields"]

    def test_missing_multiple_fields(self):
        """Test validation fails when multiple fields are missing."""
        data = {"email": "test@example.com"}
        
        with pytest.raises(ValidationException) as exc_info:
            validate_signup_data(data)
        
        assert exc_info.value.code == ErrorCode.MISSING_REQUIRED_FIELDS
        assert "name" in exc_info.value.details["missing_fields"]
        assert "phone" in exc_info.value.details["missing_fields"]


class TestPurchaseDataValidation:
    """Tests for purchase event data validation."""

    def test_valid_purchase_data(self):
        """Test validation of valid purchase data."""
        data = {
            "membership_id": "member-123",
            "amount": "25.50",
            "double_star_day": False,
            "personal_cup": False
        }
        
        result = validate_purchase_data(data)
        assert result.membership_id == "member-123"
        assert result.amount == Decimal("25.50")
        assert result.double_star_day is False
        assert result.personal_cup is False

    def test_valid_purchase_with_flags(self):
        """Test validation with double star day and personal cup flags."""
        data = {
            "membership_id": "member-123",
            "amount": "10.00",
            "double_star_day": True,
            "personal_cup": True
        }
        
        result = validate_purchase_data(data)
        assert result.double_star_day is True
        assert result.personal_cup is True

    def test_negative_purchase_amount(self):
        """Test validation fails for negative purchase amount."""
        data = {
            "membership_id": "member-123",
            "amount": "-10.00",
            "double_star_day": False,
            "personal_cup": False
        }
        
        with pytest.raises(ValidationException) as exc_info:
            validate_purchase_data(data)
        
        assert exc_info.value.code == ErrorCode.INVALID_AMOUNT
        assert "amount must be positive" in exc_info.value.message

    def test_zero_purchase_amount(self):
        """Test validation fails for zero purchase amount."""
        data = {
            "membership_id": "member-123",
            "amount": "0.00",
            "double_star_day": False,
            "personal_cup": False
        }
        
        with pytest.raises(ValidationException) as exc_info:
            validate_purchase_data(data)
        
        assert exc_info.value.code == ErrorCode.INVALID_AMOUNT

    def test_missing_membership_id(self):
        """Test validation fails when membership ID is missing."""
        data = {
            "amount": "25.50",
            "double_star_day": False,
            "personal_cup": False
        }
        
        with pytest.raises(ValidationException) as exc_info:
            validate_purchase_data(data)
        
        assert exc_info.value.code == ErrorCode.MISSING_REQUIRED_FIELDS
        assert "membership_id" in exc_info.value.details["missing_fields"]

    def test_missing_amount(self):
        """Test validation fails when amount is missing."""
        data = {
            "membership_id": "member-123",
            "double_star_day": False,
            "personal_cup": False
        }
        
        with pytest.raises(ValidationException) as exc_info:
            validate_purchase_data(data)
        
        assert exc_info.value.code == ErrorCode.MISSING_REQUIRED_FIELDS
        assert "amount" in exc_info.value.details["missing_fields"]


class TestRedemptionDataValidation:
    """Tests for redemption event data validation."""

    def test_valid_redemption_data(self):
        """Test validation of valid redemption data."""
        data = {
            "membership_id": "member-123",
            "stars_to_redeem": 100,
            "item_description": "Free coffee"
        }
        
        result = validate_redemption_data(data)
        assert result.membership_id == "member-123"
        assert result.stars_to_redeem == 100
        assert result.item_description == "Free coffee"

    def test_minimum_redemption_amount(self):
        """Test validation accepts minimum redemption of 60 stars."""
        data = {
            "membership_id": "member-123",
            "stars_to_redeem": 60,
            "item_description": "Free item"
        }
        
        result = validate_redemption_data(data)
        assert result.stars_to_redeem == 60

    def test_redemption_below_minimum(self):
        """Test validation fails for redemption below 60 stars."""
        data = {
            "membership_id": "member-123",
            "stars_to_redeem": 59,
            "item_description": "Free item"
        }
        
        with pytest.raises(ValidationException) as exc_info:
            validate_redemption_data(data)
        
        assert exc_info.value.code == ErrorCode.INVALID_REDEMPTION
        assert "minimum redemption is 60 stars" in exc_info.value.message

    def test_negative_redemption_amount(self):
        """Test validation fails for negative redemption amount."""
        data = {
            "membership_id": "member-123",
            "stars_to_redeem": -10,
            "item_description": "Free item"
        }
        
        with pytest.raises(ValidationException) as exc_info:
            validate_redemption_data(data)
        
        assert exc_info.value.code == ErrorCode.INVALID_REDEMPTION
        assert "minimum redemption is 60 stars" in exc_info.value.message

    def test_zero_redemption_amount(self):
        """Test validation fails for zero redemption amount."""
        data = {
            "membership_id": "member-123",
            "stars_to_redeem": 0,
            "item_description": "Free item"
        }
        
        with pytest.raises(ValidationException) as exc_info:
            validate_redemption_data(data)
        
        assert exc_info.value.code == ErrorCode.INVALID_REDEMPTION

    def test_missing_membership_id(self):
        """Test validation fails when membership ID is missing."""
        data = {
            "stars_to_redeem": 100,
            "item_description": "Free item"
        }
        
        with pytest.raises(ValidationException) as exc_info:
            validate_redemption_data(data)
        
        assert exc_info.value.code == ErrorCode.MISSING_REQUIRED_FIELDS
        assert "membership_id" in exc_info.value.details["missing_fields"]

    def test_missing_stars_to_redeem(self):
        """Test validation fails when stars_to_redeem is missing."""
        data = {
            "membership_id": "member-123",
            "item_description": "Free item"
        }
        
        with pytest.raises(ValidationException) as exc_info:
            validate_redemption_data(data)
        
        assert exc_info.value.code == ErrorCode.MISSING_REQUIRED_FIELDS
        assert "stars_to_redeem" in exc_info.value.details["missing_fields"]


class TestMembershipIdValidation:
    """Tests for membership ID validation."""

    def test_valid_membership_id(self):
        """Test validation of valid membership ID."""
        result = validate_membership_id("member-123")
        assert result == "member-123"

    def test_membership_id_with_whitespace(self):
        """Test validation trims whitespace from membership ID."""
        result = validate_membership_id("  member-123  ")
        assert result == "member-123"

    def test_none_membership_id(self):
        """Test validation fails for None membership ID."""
        with pytest.raises(ValidationException) as exc_info:
            validate_membership_id(None)
        
        assert exc_info.value.code == ErrorCode.INVALID_MEMBERSHIP_ID_FORMAT
        assert "required" in exc_info.value.message

    def test_empty_membership_id(self):
        """Test validation fails for empty membership ID."""
        with pytest.raises(ValidationException) as exc_info:
            validate_membership_id("")
        
        assert exc_info.value.code == ErrorCode.INVALID_MEMBERSHIP_ID_FORMAT

    def test_whitespace_only_membership_id(self):
        """Test validation fails for whitespace-only membership ID."""
        with pytest.raises(ValidationException) as exc_info:
            validate_membership_id("   ")
        
        assert exc_info.value.code == ErrorCode.INVALID_MEMBERSHIP_ID_FORMAT


class TestErrorResponseFormatter:
    """Tests for error response formatter."""

    def test_create_error_response(self):
        """Test creating a standardized error response."""
        response = create_error_response(
            code=ErrorCode.MEMBER_NOT_FOUND,
            message="Member with ID member-123 does not exist",
            details={"membership_id": "member-123"}
        )
        
        assert "error" in response
        assert response["error"]["code"] == ErrorCode.MEMBER_NOT_FOUND
        assert "member-123" in response["error"]["message"]
        assert response["error"]["details"]["membership_id"] == "member-123"
        assert "timestamp" in response["error"]

    def test_create_error_response_without_details(self):
        """Test creating error response without additional details."""
        response = create_error_response(
            code=ErrorCode.INVALID_AMOUNT,
            message="Invalid purchase amount"
        )
        
        assert "error" in response
        assert response["error"]["code"] == ErrorCode.INVALID_AMOUNT
        assert response["error"]["message"] == "Invalid purchase amount"
        assert response["error"]["details"] == {}
        assert "timestamp" in response["error"]


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_very_large_purchase_amount(self):
        """Test validation accepts very large purchase amounts."""
        data = {
            "membership_id": "member-123",
            "amount": "999999.99",
            "double_star_day": False,
            "personal_cup": False
        }
        
        result = validate_purchase_data(data)
        assert result.amount == Decimal("999999.99")

    def test_very_small_positive_purchase_amount(self):
        """Test validation accepts very small positive amounts."""
        data = {
            "membership_id": "member-123",
            "amount": "0.01",
            "double_star_day": False,
            "personal_cup": False
        }
        
        result = validate_purchase_data(data)
        assert result.amount == Decimal("0.01")

    def test_very_large_redemption_amount(self):
        """Test validation accepts very large redemption amounts."""
        data = {
            "membership_id": "member-123",
            "stars_to_redeem": 999999,
            "item_description": "Premium item"
        }
        
        result = validate_redemption_data(data)
        assert result.stars_to_redeem == 999999
