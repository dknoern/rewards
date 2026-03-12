"""Unit tests for enrollment handler."""

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import pytest
from enrollment.handler import handler
from common.models import MemberProfile, Tier, Transaction, TransactionType
from common.validation import ValidationException


@pytest.fixture
def valid_signup_event():
    """Create a valid signup event."""
    return {
        'event_type': 'rewards.member.signup',
        'transaction_id': str(uuid.uuid4()),
        'timestamp': datetime.utcnow().isoformat(),
        'data': {
            'email': 'test@example.com',
            'name': 'Test User',
            'phone': '+1234567890'
        }
    }


@pytest.fixture
def mock_db_client():
    """Create a mock DynamoDB client."""
    with patch('enrollment.handler.DynamoDBClient') as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance
        yield mock_instance


class TestEnrollmentHandler:
    """Test cases for enrollment handler."""
    
    def test_successful_enrollment(self, valid_signup_event, mock_db_client):
        """Test successful member enrollment with valid data."""
        # Arrange
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.create_member.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        response = handler(valid_signup_event, None)
        
        # Assert
        assert response['statusCode'] == 201
        body = json.loads(response['body'])
        assert body['message'] == 'Member enrolled successfully'
        assert 'membershipId' in body
        assert body['tier'] == 'Green'
        assert body['transactionId'] == valid_signup_event['transaction_id']
        
        # Verify DynamoDB calls
        mock_db_client.check_transaction_exists.assert_called_once_with(
            valid_signup_event['transaction_id']
        )
        mock_db_client.create_member.assert_called_once()
        mock_db_client.record_transaction.assert_called_once()
        
        # Verify member profile created with correct values
        created_profile = mock_db_client.create_member.call_args[0][0]
        assert isinstance(created_profile, MemberProfile)
        assert created_profile.email == 'test@example.com'
        assert created_profile.name == 'Test User'
        assert created_profile.phone == '+1234567890'
        assert created_profile.tier == Tier.GREEN
        assert created_profile.star_balance == 0
        assert created_profile.annual_star_count == 0
        assert isinstance(created_profile.enrollment_date, datetime)
        assert isinstance(created_profile.tier_since, datetime)
        assert isinstance(created_profile.next_tier_evaluation, datetime)
        
        # Verify next tier evaluation is 365 days from enrollment
        days_diff = (created_profile.next_tier_evaluation - created_profile.enrollment_date).days
        assert days_diff == 365
    
    def test_idempotent_duplicate_transaction(self, valid_signup_event, mock_db_client):
        """Test idempotent handling of duplicate transaction ID."""
        # Arrange
        existing_membership_id = str(uuid.uuid4())
        mock_db_client.check_transaction_exists.return_value = {
            'membershipId': existing_membership_id,
            'transactionId': valid_signup_event['transaction_id']
        }
        
        # Act
        response = handler(valid_signup_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['message'] == 'Member already enrolled (idempotent)'
        assert body['membershipId'] == existing_membership_id
        assert body['transactionId'] == valid_signup_event['transaction_id']
        
        # Verify create_member was NOT called
        mock_db_client.create_member.assert_not_called()
        mock_db_client.record_transaction.assert_not_called()
    
    def test_missing_required_fields(self, mock_db_client):
        """Test error handling for missing required fields."""
        # Arrange - missing 'data' field
        invalid_event = {
            'event_type': 'rewards.member.signup',
            'transaction_id': str(uuid.uuid4()),
            'timestamp': datetime.utcnow().isoformat()
            # Missing 'data' field
        }
        
        # Act
        response = handler(invalid_event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error']['code'] == 'MISSING_REQUIRED_FIELDS'
        assert 'data' in body['error']['message'].lower()
    
    def test_missing_signup_data_fields(self, mock_db_client):
        """Test error handling for missing fields in signup data."""
        # Arrange - missing 'email' field
        invalid_event = {
            'event_type': 'rewards.member.signup',
            'transaction_id': str(uuid.uuid4()),
            'timestamp': datetime.utcnow().isoformat(),
            'data': {
                'name': 'Test User',
                'phone': '+1234567890'
                # Missing 'email' field
            }
        }
        mock_db_client.check_transaction_exists.return_value = None
        
        # Act
        response = handler(invalid_event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error']['code'] == 'MISSING_REQUIRED_FIELDS'
        assert 'email' in body['error']['message'].lower()
    
    def test_invalid_data_types(self, mock_db_client):
        """Test error handling for invalid data types."""
        # Arrange - invalid timestamp format
        invalid_event = {
            'event_type': 'rewards.member.signup',
            'transaction_id': str(uuid.uuid4()),
            'timestamp': 'not-a-valid-timestamp',
            'data': {
                'email': 'test@example.com',
                'name': 'Test User',
                'phone': '+1234567890'
            }
        }
        
        # Act
        response = handler(invalid_event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error']['code'] == 'INVALID_DATA_TYPE'
    
    def test_duplicate_enrollment_error(self, valid_signup_event, mock_db_client):
        """Test error when attempting to create duplicate member."""
        # Arrange
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.create_member.side_effect = ValueError(
            "Member test-id already exists"
        )
        
        # Act
        response = handler(valid_signup_event, None)
        
        # Assert
        assert response['statusCode'] == 422
        body = json.loads(response['body'])
        assert body['error']['code'] == 'DUPLICATE_ENROLLMENT'
        assert 'already exists' in body['error']['message']
    
    def test_database_error_handling(self, valid_signup_event, mock_db_client):
        """Test handling of database errors."""
        # Arrange
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.create_member.side_effect = Exception("Database connection failed")
        
        # Act
        response = handler(valid_signup_event, None)
        
        # Assert
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert body['error']['code'] == 'INTERNAL_ERROR'
        assert 'unexpected error' in body['error']['message'].lower()
    
    def test_transaction_recorded_correctly(self, valid_signup_event, mock_db_client):
        """Test that enrollment transaction is recorded with correct details."""
        # Arrange
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.create_member.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        response = handler(valid_signup_event, None)
        
        # Assert
        assert response['statusCode'] == 201
        
        # Verify transaction recorded
        mock_db_client.record_transaction.assert_called_once()
        recorded_txn = mock_db_client.record_transaction.call_args[0][0]
        assert isinstance(recorded_txn, Transaction)
        assert recorded_txn.transaction_id == valid_signup_event['transaction_id']
        assert recorded_txn.type == TransactionType.TIER_CHANGE
        assert isinstance(recorded_txn.timestamp, datetime)
        assert 'enrolled' in recorded_txn.description.lower()
        assert 'Green' in recorded_txn.description
    
    def test_membership_id_is_uuid(self, valid_signup_event, mock_db_client):
        """Test that generated membership ID is a valid UUID."""
        # Arrange
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.create_member.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        response = handler(valid_signup_event, None)
        
        # Assert
        assert response['statusCode'] == 201
        body = json.loads(response['body'])
        membership_id = body['membershipId']
        
        # Verify it's a valid UUID
        try:
            uuid.UUID(membership_id)
        except ValueError:
            pytest.fail(f"Membership ID '{membership_id}' is not a valid UUID")
    
    def test_enrollment_timestamp_recorded(self, valid_signup_event, mock_db_client):
        """Test that enrollment timestamp is recorded correctly."""
        # Arrange
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.create_member.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        before_enrollment = datetime.utcnow()
        
        # Act
        response = handler(valid_signup_event, None)
        
        after_enrollment = datetime.utcnow()
        
        # Assert
        assert response['statusCode'] == 201
        
        # Verify enrollment date is within expected range
        created_profile = mock_db_client.create_member.call_args[0][0]
        assert before_enrollment <= created_profile.enrollment_date <= after_enrollment
        assert before_enrollment <= created_profile.tier_since <= after_enrollment
    
    def test_initial_tier_evaluation_date_set(self, valid_signup_event, mock_db_client):
        """Test that initial tier evaluation date is set to 12 months from enrollment."""
        # Arrange
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.create_member.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        response = handler(valid_signup_event, None)
        
        # Assert
        assert response['statusCode'] == 201
        
        # Verify tier evaluation date
        created_profile = mock_db_client.create_member.call_args[0][0]
        expected_eval_date = created_profile.enrollment_date + timedelta(days=365)
        
        # Allow for small time differences (within 1 second)
        time_diff = abs((created_profile.next_tier_evaluation - expected_eval_date).total_seconds())
        assert time_diff < 1
    
    def test_all_required_profile_fields_initialized(self, valid_signup_event, mock_db_client):
        """Test that all required member profile fields are initialized."""
        # Arrange
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.create_member.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        response = handler(valid_signup_event, None)
        
        # Assert
        assert response['statusCode'] == 201
        
        # Verify all required fields are present
        created_profile = mock_db_client.create_member.call_args[0][0]
        assert created_profile.membership_id is not None
        assert created_profile.email == 'test@example.com'
        assert created_profile.name == 'Test User'
        assert created_profile.phone == '+1234567890'
        assert created_profile.tier == Tier.GREEN
        assert created_profile.star_balance == 0
        assert created_profile.annual_star_count == 0
        assert created_profile.enrollment_date is not None
        assert created_profile.tier_since is not None
        assert created_profile.next_tier_evaluation is not None
        # last_qualifying_activity should be None initially
        assert created_profile.last_qualifying_activity is None
