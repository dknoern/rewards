"""Unit tests for redemption handler."""

import json
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from redemption.handler import handler
from common.models import MemberProfile, Tier, Transaction, TransactionType
from common.validation import ErrorCode


@pytest.fixture
def valid_redemption_event():
    """Create a valid redemption event."""
    return {
        'event_type': 'rewards.transaction.redemption',
        'transaction_id': str(uuid.uuid4()),
        'timestamp': datetime.utcnow().isoformat(),
        'data': {
            'membership_id': str(uuid.uuid4()),
            'stars_to_redeem': 100,
            'item_description': 'Free coffee'
        }
    }


@pytest.fixture
def mock_member():
    """Create a mock member profile with sufficient balance."""
    return MemberProfile(
        membership_id=str(uuid.uuid4()),
        email='test@example.com',
        name='Test User',
        phone='555-0100',
        tier=Tier.GREEN,
        star_balance=200,
        annual_star_count=200,
        enrollment_date=datetime.utcnow(),
        tier_since=datetime.utcnow(),
        next_tier_evaluation=datetime.utcnow()
    )


@pytest.fixture
def mock_db_client():
    """Create a mock DynamoDB client."""
    with patch('redemption.handler.DynamoDBClient') as mock_client_class:
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        yield mock_client


class TestRedemptionHandler:
    """Test suite for redemption handler."""
    
    def test_successful_redemption(self, valid_redemption_event, mock_member, mock_db_client):
        """Test successful redemption with sufficient balance."""
        # Arrange
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.get_member.return_value = mock_member
        mock_db_client.update_member_balance.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        response = handler(valid_redemption_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['message'] == 'Redemption processed successfully'
        assert body['starsRedeemed'] == 100
        assert body['itemDescription'] == 'Free coffee'
        assert body['membershipId'] == valid_redemption_event['data']['membership_id']
        
        # Verify balance was updated
        mock_db_client.update_member_balance.assert_called_once()
        call_args = mock_db_client.update_member_balance.call_args
        assert call_args[1]['membership_id'] == valid_redemption_event['data']['membership_id']
        assert call_args[1]['star_delta'] == -100
        assert call_args[1]['annual_star_delta'] == 0
        
        # Verify transaction was recorded
        mock_db_client.record_transaction.assert_called_once()
        txn = mock_db_client.record_transaction.call_args[0][0]
        assert txn.type == TransactionType.REDEMPTION
        assert txn.stars_redeemed == 100
        assert txn.description == 'Free coffee'
    
    def test_redemption_at_minimum_threshold(self, valid_redemption_event, mock_member, mock_db_client):
        """Test redemption at exactly 60 stars (minimum threshold)."""
        # Arrange
        valid_redemption_event['data']['stars_to_redeem'] = 60
        mock_member.star_balance = 60
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.get_member.return_value = mock_member
        mock_db_client.update_member_balance.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        response = handler(valid_redemption_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['starsRedeemed'] == 60
    
    def test_redemption_below_minimum_threshold(self, valid_redemption_event, mock_db_client):
        """Test redemption below 60 stars is rejected."""
        # Arrange
        valid_redemption_event['data']['stars_to_redeem'] = 59
        mock_db_client.check_transaction_exists.return_value = None
        
        # Act
        response = handler(valid_redemption_event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error']['code'] == ErrorCode.INVALID_REDEMPTION
        assert 'minimum redemption is 60 stars' in body['error']['message'].lower()
    
    def test_redemption_with_insufficient_balance(self, valid_redemption_event, mock_member, mock_db_client):
        """Test redemption fails when member has insufficient stars."""
        # Arrange
        mock_member.star_balance = 50
        valid_redemption_event['data']['stars_to_redeem'] = 100
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.get_member.return_value = mock_member
        
        # Act
        response = handler(valid_redemption_event, None)
        
        # Assert
        assert response['statusCode'] == 422
        body = json.loads(response['body'])
        assert body['error']['code'] == ErrorCode.INSUFFICIENT_STARS
        assert 'insufficient star balance' in body['error']['message'].lower()
        assert body['error']['details']['availableStars'] == 50
        assert body['error']['details']['requestedStars'] == 100
        
        # Verify balance was NOT updated
        mock_db_client.update_member_balance.assert_not_called()
        mock_db_client.record_transaction.assert_not_called()
    
    def test_redemption_with_exact_balance(self, valid_redemption_event, mock_member, mock_db_client):
        """Test redemption when stars exactly match balance."""
        # Arrange
        mock_member.star_balance = 100
        valid_redemption_event['data']['stars_to_redeem'] = 100
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.get_member.return_value = mock_member
        mock_db_client.update_member_balance.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        response = handler(valid_redemption_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['starsRedeemed'] == 100
    
    def test_redemption_member_not_found(self, valid_redemption_event, mock_db_client):
        """Test redemption fails when member doesn't exist."""
        # Arrange
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.get_member.return_value = None
        
        # Act
        response = handler(valid_redemption_event, None)
        
        # Assert
        assert response['statusCode'] == 422
        body = json.loads(response['body'])
        assert body['error']['code'] == ErrorCode.MEMBER_NOT_FOUND
        assert 'does not exist' in body['error']['message']
        
        # Verify no updates were made
        mock_db_client.update_member_balance.assert_not_called()
        mock_db_client.record_transaction.assert_not_called()
    
    def test_redemption_idempotency(self, valid_redemption_event, mock_db_client):
        """Test duplicate redemption returns cached result without reprocessing."""
        # Arrange
        existing_txn = {
            'membershipId': valid_redemption_event['data']['membership_id'],
            'starsRedeemed': 100,
            'transactionId': valid_redemption_event['transaction_id']
        }
        mock_db_client.check_transaction_exists.return_value = existing_txn
        
        # Act
        response = handler(valid_redemption_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'already processed' in body['message'].lower()
        assert body['starsRedeemed'] == 100
        
        # Verify no processing occurred
        mock_db_client.get_member.assert_not_called()
        mock_db_client.update_member_balance.assert_not_called()
        mock_db_client.record_transaction.assert_not_called()
    
    def test_redemption_missing_required_fields(self, mock_db_client):
        """Test redemption fails with missing required fields."""
        # Arrange
        invalid_event = {
            'event_type': 'rewards.transaction.redemption',
            'transaction_id': str(uuid.uuid4()),
            'timestamp': datetime.utcnow().isoformat(),
            'data': {
                'membership_id': str(uuid.uuid4())
                # Missing stars_to_redeem and item_description
            }
        }
        mock_db_client.check_transaction_exists.return_value = None
        
        # Act
        response = handler(invalid_event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error']['code'] == ErrorCode.MISSING_REQUIRED_FIELDS
        assert 'missing required fields' in body['error']['message'].lower()
    
    def test_redemption_invalid_data_types(self, mock_db_client):
        """Test redemption fails with invalid data types."""
        # Arrange
        invalid_event = {
            'event_type': 'rewards.transaction.redemption',
            'transaction_id': str(uuid.uuid4()),
            'timestamp': datetime.utcnow().isoformat(),
            'data': {
                'membership_id': str(uuid.uuid4()),
                'stars_to_redeem': 'not_a_number',  # Invalid type
                'item_description': 'Free coffee'
            }
        }
        mock_db_client.check_transaction_exists.return_value = None
        
        # Act
        response = handler(invalid_event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error']['code'] in [ErrorCode.INVALID_DATA_TYPE, ErrorCode.INVALID_REDEMPTION]
    
    def test_redemption_negative_stars(self, mock_db_client):
        """Test redemption fails with negative star amount."""
        # Arrange
        invalid_event = {
            'event_type': 'rewards.transaction.redemption',
            'transaction_id': str(uuid.uuid4()),
            'timestamp': datetime.utcnow().isoformat(),
            'data': {
                'membership_id': str(uuid.uuid4()),
                'stars_to_redeem': -50,
                'item_description': 'Free coffee'
            }
        }
        mock_db_client.check_transaction_exists.return_value = None
        
        # Act
        response = handler(invalid_event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error']['code'] == ErrorCode.INVALID_REDEMPTION
    
    def test_redemption_conditional_update_race_condition(self, valid_redemption_event, mock_member, mock_db_client):
        """Test redemption handles race condition where balance becomes insufficient."""
        # Arrange
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.get_member.return_value = mock_member
        # Simulate conditional update failure (balance changed between check and update)
        mock_db_client.update_member_balance.side_effect = ValueError("Insufficient star balance")
        
        # Act
        response = handler(valid_redemption_event, None)
        
        # Assert
        assert response['statusCode'] == 422
        body = json.loads(response['body'])
        assert body['error']['code'] == ErrorCode.INSUFFICIENT_STARS
        
        # Verify transaction was NOT recorded
        mock_db_client.record_transaction.assert_not_called()
    
    def test_redemption_with_different_tiers(self, valid_redemption_event, mock_member, mock_db_client):
        """Test redemption works for all tier levels."""
        tiers = [Tier.GREEN, Tier.GOLD, Tier.RESERVE]
        
        for tier in tiers:
            # Arrange
            mock_member.tier = tier
            mock_member.star_balance = 200
            valid_redemption_event['transaction_id'] = str(uuid.uuid4())  # New transaction ID
            mock_db_client.check_transaction_exists.return_value = None
            mock_db_client.get_member.return_value = mock_member
            mock_db_client.update_member_balance.return_value = True
            mock_db_client.record_transaction.return_value = True
            
            # Act
            response = handler(valid_redemption_event, None)
            
            # Assert
            assert response['statusCode'] == 200, f"Failed for tier {tier}"
            body = json.loads(response['body'])
            assert body['starsRedeemed'] == 100
    
    def test_redemption_records_correct_transaction_details(self, valid_redemption_event, mock_member, mock_db_client):
        """Test redemption records transaction with all required details."""
        # Arrange
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.get_member.return_value = mock_member
        mock_db_client.update_member_balance.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        response = handler(valid_redemption_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        
        # Verify transaction details
        mock_db_client.record_transaction.assert_called_once()
        txn = mock_db_client.record_transaction.call_args[0][0]
        assert isinstance(txn, Transaction)
        assert txn.transaction_id == valid_redemption_event['transaction_id']
        assert txn.membership_id == valid_redemption_event['data']['membership_id']
        assert txn.type == TransactionType.REDEMPTION
        assert txn.stars_redeemed == 100
        assert txn.description == 'Free coffee'
        assert txn.stars_earned is None
        assert txn.purchase_amount is None
        assert isinstance(txn.timestamp, datetime)
    
    def test_redemption_database_error(self, valid_redemption_event, mock_member, mock_db_client):
        """Test redemption handles database errors gracefully."""
        # Arrange
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.get_member.return_value = mock_member
        mock_db_client.update_member_balance.side_effect = Exception("Database connection error")
        
        # Act
        response = handler(valid_redemption_event, None)
        
        # Assert
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert body['error']['code'] == ErrorCode.INTERNAL_ERROR
        assert 'unexpected error' in body['error']['message'].lower()
    
    def test_redemption_large_amount(self, valid_redemption_event, mock_member, mock_db_client):
        """Test redemption with large star amount."""
        # Arrange
        large_amount = 10000
        mock_member.star_balance = 15000
        valid_redemption_event['data']['stars_to_redeem'] = large_amount
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.get_member.return_value = mock_member
        mock_db_client.update_member_balance.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        response = handler(valid_redemption_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['starsRedeemed'] == large_amount
