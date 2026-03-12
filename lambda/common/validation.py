"""Input validation utilities for event messages and API requests."""

from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import ValidationError
from common.models import (
    EventMessage,
    SignupEventData,
    PurchaseEventData,
    RedemptionEventData,
    ErrorResponse
)


# Standardized error codes
class ErrorCode:
    """Standardized error codes for the rewards system."""
    
    # Validation errors (HTTP 400)
    MISSING_REQUIRED_FIELDS = "MISSING_REQUIRED_FIELDS"
    INVALID_DATA_TYPE = "INVALID_DATA_TYPE"
    INVALID_AMOUNT = "INVALID_AMOUNT"
    INVALID_REDEMPTION = "INVALID_REDEMPTION"
    INVALID_MEMBERSHIP_ID_FORMAT = "INVALID_MEMBERSHIP_ID_FORMAT"
    
    # Business logic errors (HTTP 422)
    DUPLICATE_ENROLLMENT = "DUPLICATE_ENROLLMENT"
    MEMBER_NOT_FOUND = "MEMBER_NOT_FOUND"
    INSUFFICIENT_STARS = "INSUFFICIENT_STARS"
    REDEMPTION_BELOW_MINIMUM = "REDEMPTION_BELOW_MINIMUM"
    
    # System errors (HTTP 500)
    INTERNAL_ERROR = "INTERNAL_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"


class ValidationException(Exception):
    """Exception raised for validation errors."""
    
    def __init__(
        self, 
        message: str, 
        code: str = ErrorCode.INVALID_DATA_TYPE,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)


def validate_event_message(event: Dict[str, Any]) -> EventMessage:
    """
    Validate the base event message structure.
    
    Args:
        event: Raw event dictionary
        
    Returns:
        Validated EventMessage object
        
    Raises:
        ValidationException: If validation fails
    """
    try:
        return EventMessage(**event)
    except ValidationError as e:
        missing_fields = []
        invalid_fields = []
        
        for error in e.errors():
            field = ".".join(str(loc) for loc in error["loc"])
            # Check for both "missing" type and "field required" message
            if error["type"] == "missing" or "field required" in error["msg"]:
                missing_fields.append(field)
            else:
                invalid_fields.append(f"{field}: {error['msg']}")
        
        if missing_fields:
            raise ValidationException(
                f"Missing required fields: {', '.join(missing_fields)}",
                code=ErrorCode.MISSING_REQUIRED_FIELDS,
                details={"missing_fields": missing_fields}
            )
        else:
            raise ValidationException(
                f"Invalid data types: {'; '.join(invalid_fields)}",
                code=ErrorCode.INVALID_DATA_TYPE,
                details={"invalid_fields": invalid_fields}
            )


def validate_signup_data(data: Dict[str, Any]) -> SignupEventData:
    """
    Validate signup event data.
    
    Args:
        data: Event data dictionary
        
    Returns:
        Validated SignupEventData object
        
    Raises:
        ValidationException: If validation fails
    """
    try:
        return SignupEventData(**data)
    except ValidationError as e:
        missing_fields = []
        invalid_fields = []
        
        for err in e.errors():
            field = ".".join(str(loc) for loc in err["loc"])
            # Check for both "missing" type and "field required" message
            if err["type"] == "missing" or "field required" in err["msg"]:
                missing_fields.append(field)
            else:
                invalid_fields.append({"field": field, "message": err["msg"]})
        
        if missing_fields:
            raise ValidationException(
                f"Missing required fields: {', '.join(missing_fields)}",
                code=ErrorCode.MISSING_REQUIRED_FIELDS,
                details={"missing_fields": missing_fields}
            )
        else:
            raise ValidationException(
                "Invalid signup data",
                code=ErrorCode.INVALID_DATA_TYPE,
                details={"errors": invalid_fields}
            )


def validate_purchase_data(data: Dict[str, Any]) -> PurchaseEventData:
    """
    Validate purchase event data.
    
    Args:
        data: Event data dictionary
        
    Returns:
        Validated PurchaseEventData object
        
    Raises:
        ValidationException: If validation fails
    """
    try:
        return PurchaseEventData(**data)
    except ValidationError as e:
        missing_fields = []
        
        for err in e.errors():
            field = ".".join(str(loc) for loc in err["loc"])
            
            # Check for missing fields first (both "missing" type and "field required" message)
            if err["type"] == "missing" or "field required" in err["msg"]:
                missing_fields.append(field)
                continue
            
            # Check for negative amount validation
            if "amount" in field and ("greater than 0" in err["msg"] or "greater than" in err["msg"]):
                raise ValidationException(
                    "Invalid purchase amount: amount must be positive",
                    code=ErrorCode.INVALID_AMOUNT,
                    details={"field": "amount", "value": data.get("amount")}
                )
        
        if missing_fields:
            raise ValidationException(
                f"Missing required fields: {', '.join(missing_fields)}",
                code=ErrorCode.MISSING_REQUIRED_FIELDS,
                details={"missing_fields": missing_fields}
            )
        
        # Generic validation error
        raise ValidationException(
            "Invalid purchase data",
            code=ErrorCode.INVALID_DATA_TYPE,
            details={"errors": [{"field": ".".join(str(loc) for loc in err["loc"]), 
                                "message": err["msg"]} for err in e.errors()]}
        )


def validate_redemption_data(data: Dict[str, Any]) -> RedemptionEventData:
    """
    Validate redemption event data.
    
    Args:
        data: Event data dictionary
        
    Returns:
        Validated RedemptionEventData object
        
    Raises:
        ValidationException: If validation fails
    """
    try:
        return RedemptionEventData(**data)
    except ValidationError as e:
        missing_fields = []
        
        for err in e.errors():
            field = ".".join(str(loc) for loc in err["loc"])
            
            # Check for missing fields first (both "missing" type and "field required" message)
            if err["type"] == "missing" or "field required" in err["msg"]:
                missing_fields.append(field)
                continue
            
            # Check for negative or below minimum redemption
            if "stars_to_redeem" in field:
                if "greater than 0" in err["msg"] or "greater than or equal to 60" in err["msg"]:
                    raise ValidationException(
                        "Invalid redemption amount: minimum redemption is 60 stars",
                        code=ErrorCode.INVALID_REDEMPTION,
                        details={"field": "stars_to_redeem", "value": data.get("stars_to_redeem")}
                    )
        
        if missing_fields:
            raise ValidationException(
                f"Missing required fields: {', '.join(missing_fields)}",
                code=ErrorCode.MISSING_REQUIRED_FIELDS,
                details={"missing_fields": missing_fields}
            )
        
        # Generic validation error
        raise ValidationException(
            "Invalid redemption data",
            code=ErrorCode.INVALID_DATA_TYPE,
            details={"errors": [{"field": ".".join(str(loc) for loc in err["loc"]), 
                                "message": err["msg"]} for err in e.errors()]}
        )


def validate_membership_id(membership_id: Optional[str]) -> str:
    """
    Validate membership ID format.
    
    Args:
        membership_id: Membership ID to validate
        
    Returns:
        Validated membership ID
        
    Raises:
        ValidationException: If membership ID is invalid
    """
    if not membership_id:
        raise ValidationException(
            "Membership ID is required",
            code=ErrorCode.INVALID_MEMBERSHIP_ID_FORMAT
        )
    
    if not isinstance(membership_id, str) or len(membership_id.strip()) == 0:
        raise ValidationException(
            "Invalid membership ID format",
            code=ErrorCode.INVALID_MEMBERSHIP_ID_FORMAT
        )
    
    return membership_id.strip()


def create_error_response(code: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Create a standardized error response.
    
    Args:
        code: Error code (e.g., "MEMBER_NOT_FOUND")
        message: Human-readable error message
        details: Optional additional error details
        
    Returns:
        Error response dictionary
    """
    error_data = {
        "code": code,
        "message": message,
        "details": details or {},
        "timestamp": datetime.utcnow().isoformat()
    }
    
    return ErrorResponse(error=error_data).dict()
