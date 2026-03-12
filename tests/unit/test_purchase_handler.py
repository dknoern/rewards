"""Unit tests for purchase handler."""

import json
import uuid
from datetime import datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch
import pytest
from purchase.handler import handler
from common.models import MemberProfile, Tier, Transaction, TransactionType


@pytest.fixture
def valid_purchase_event():
    """Create a valid purchase event."""
    return {
        'event_type': 'rewards.transaction.purchase',
        'transaction_id': str(uuid.uuid4()),
        'timestamp': datetime.utcnow().isoformat(),
        'data': {
            'membership_id': str(uuid.uuid4()),
            'amount': '10.00',
            'double_star_day': False,
            'personal_cup': False
        }
    }


@pytest.fixture
def mock_db_client():
    """Create a mock DynamoDB client."""
    with patch('purchase.handler.DynamoDBClient') as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_green_member():
    """Create a mock Green tier member."""
    return MemberProfile(
        membership_id=str(uuid.uuid4()),
        email='test@example.com',
        name='Test User',
        phone='+1234567890',
        tier=Tier.GREEN,
        star_balance=100,
        annual_star_count=50,
        enrollment_date=datetime.utcnow(),
        tier_since=datetime.utcnow(),
        next_tier_evaluation=datetime.utcnow()
    )


@pytest.fixture
def mock_gold_member():
    """Create a mock Gold tier member."""
    return MemberProfile(
        membership_id=str(uuid.uuid4()),
        email='gold@example.com',
        name='Gold User',
        phone='+1234567890',
        tier=Tier.GOLD,
        star_balance=500,
        annual_star_count=600,
        enrollment_date=datetime.utcnow(),
        tier_since=datetime.utcnow(),
        next_tier_evaluation=datetime.utcnow()
    )


@pytest.fixture
def mock_reserve_member():
    """Create a mock Reserve tier member."""
    return MemberProfile(
        membership_id=str(uuid.uuid4()),
        email='reserve@example.com',
        name='Reserve User',
        phone='+1234567890',
        tier=Tier.RESERVE,
        star_balance=3000,
        annual_star_count=2500,
        enrollment_date=datetime.utcnow(),
        tier_since=datetime.utcnow(),
        next_tier_evaluation=datetime.utcnow()
    )


class TestPurchaseHandler:
    """Test cases for purchase handler."""
    
    def test_successful_purchase_green_tier(self, valid_purchase_event, mock_db_client, mock_green_member):
        """Test successful purchase processing for Green tier member."""
        # Arrange
        valid_purchase_event['data']['membership_id'] = mock_green_member.membership_id
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.get_member.return_value = mock_green_member
        mock_db_client.update_member_balance.return_value = True
        mock_db_client.create_star_ledger_entry.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        response = handler(valid_purchase_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['message'] == 'Purchase processed successfully'
        assert body['membershipId'] == mock_green_member.membership_id
        assert body['starsEarned'] == 10  # $10 * 1.0 (Green rate) = 10 stars
        assert body['purchaseAmount'] == '10.00'
        
        # Verify DynamoDB calls
        mock_db_client.check_transaction_exists.assert_called_once()
        mock_db_client.get_member.assert_called_once_with(mock_green_member.membership_id)
        mock_db_client.update_member_balance.assert_called_once()
        mock_db_client.create_star_ledger_entry.assert_called_once()
        mock_db_client.record_transaction.assert_called_once()
    
    def test_successful_purchase_gold_tier(self, valid_purchase_event, mock_db_client, mock_gold_member):
        """Test successful purchase processing for Gold tier member."""
        # Arrange
        valid_purchase_event['data']['membership_id'] = mock_gold_member.membership_id
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.get_member.return_value = mock_gold_member
        mock_db_client.update_member_balance.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        response = handler(valid_purchase_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['starsEarned'] == 12  # $10 * 1.2 (Gold rate) = 12 stars
        
        # Verify star ledger entry NOT created for Gold tier
        mock_db_client.create_star_ledger_entry.assert_not_called()
    
    def test_successful_purchase_reserve_tier(self, valid_purchase_event, mock_db_client, mock_reserve_member):
        """Test successful purchase processing for Reserve tier member."""
        # Arrange
        valid_purchase_event['data']['membership_id'] = mock_reserve_member.membership_id
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.get_member.return_value = mock_reserve_member
        mock_db_client.update_member_balance.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        response = handler(valid_purchase_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['starsEarned'] == 17  # $10 * 1.7 (Reserve rate) = 17 stars
        
        # Verify star ledger entry NOT created for Reserve tier
        mock_db_client.create_star_ledger_entry.assert_not_called()
    
    def test_purchase_with_double_star_day(self, valid_purchase_event, mock_db_client, mock_green_member):
        """Test purchase on double star day applies 2x multiplier."""
        # Arrange
        valid_purchase_event['data']['membership_id'] = mock_green_member.membership_id
        valid_purchase_event['data']['double_star_day'] = True
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.get_member.return_value = mock_green_member
        mock_db_client.update_member_balance.return_value = True
        mock_db_client.create_star_ledger_entry.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        response = handler(valid_purchase_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['starsEarned'] == 20  # $10 * 1.0 * 2.0 = 20 stars
    
    def test_purchase_with_personal_cup(self, valid_purchase_event, mock_db_client, mock_green_member):
        """Test purchase with personal cup applies 2x multiplier."""
        # Arrange
        valid_purchase_event['data']['membership_id'] = mock_green_member.membership_id
        valid_purchase_event['data']['personal_cup'] = True
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.get_member.return_value = mock_green_member
        mock_db_client.update_member_balance.return_value = True
        mock_db_client.create_star_ledger_entry.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        response = handler(valid_purchase_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['starsEarned'] == 20  # $10 * 1.0 * 2.0 = 20 stars
    
    def test_purchase_with_both_multipliers(self, valid_purchase_event, mock_db_client, mock_gold_member):
        """Test purchase with both double star day and personal cup applies 4x multiplier."""
        # Arrange
        valid_purchase_event['data']['membership_id'] = mock_gold_member.membership_id
        valid_purchase_event['data']['double_star_day'] = True
        valid_purchase_event['data']['personal_cup'] = True
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.get_member.return_value = mock_gold_member
        mock_db_client.update_member_balance.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        response = handler(valid_purchase_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['starsEarned'] == 48  # $10 * 1.2 * 2.0 * 2.0 = 48 stars
    
    def test_idempotent_duplicate_transaction(self, valid_purchase_event, mock_db_client):
        """Test idempotent handling of duplicate transaction ID."""
        # Arrange
        existing_membership_id = str(uuid.uuid4())
        mock_db_client.check_transaction_exists.return_value = {
            'membershipId': existing_membership_id,
            'transactionId': valid_purchase_event['transaction_id'],
            'starsEarned': 15
        }
        
        # Act
        response = handler(valid_purchase_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['message'] == 'Purchase already processed (idempotent)'
        assert body['membershipId'] == existing_membership_id
        assert body['starsEarned'] == 15
        
        # Verify no processing occurred
        mock_db_client.get_member.assert_not_called()
        mock_db_client.update_member_balance.assert_not_called()
        mock_db_client.record_transaction.assert_not_called()
    
    def test_invalid_membership_id(self, valid_purchase_event, mock_db_client):
        """Test error when membership ID does not exist."""
        # Arrange
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.get_member.return_value = None
        
        # Act
        response = handler(valid_purchase_event, None)
        
        # Assert
        assert response['statusCode'] == 422
        body = json.loads(response['body'])
        assert body['error']['code'] == 'MEMBER_NOT_FOUND'
        assert 'does not exist' in body['error']['message']
    
    def test_missing_required_fields(self, mock_db_client):
        """Test error handling for missing required fields."""
        # Arrange - missing 'data' field
        invalid_event = {
            'event_type': 'rewards.transaction.purchase',
            'transaction_id': str(uuid.uuid4()),
            'timestamp': datetime.utcnow().isoformat()
        }
        
        # Act
        response = handler(invalid_event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error']['code'] == 'MISSING_REQUIRED_FIELDS'
    
    def test_missing_purchase_data_fields(self, mock_db_client):
        """Test error handling for missing fields in purchase data."""
        # Arrange - missing 'amount' field
        invalid_event = {
            'event_type': 'rewards.transaction.purchase',
            'transaction_id': str(uuid.uuid4()),
            'timestamp': datetime.utcnow().isoformat(),
            'data': {
                'membership_id': str(uuid.uuid4()),
                'double_star_day': False,
                'personal_cup': False
            }
        }
        mock_db_client.check_transaction_exists.return_value = None
        
        # Act
        response = handler(invalid_event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error']['code'] == 'MISSING_REQUIRED_FIELDS'
    
    def test_negative_purchase_amount(self, mock_db_client):
        """Test error handling for negative purchase amount."""
        # Arrange
        invalid_event = {
            'event_type': 'rewards.transaction.purchase',
            'transaction_id': str(uuid.uuid4()),
            'timestamp': datetime.utcnow().isoformat(),
            'data': {
                'membership_id': str(uuid.uuid4()),
                'amount': '-10.00',
                'double_star_day': False,
                'personal_cup': False
            }
        }
        mock_db_client.check_transaction_exists.return_value = None
        
        # Act
        response = handler(invalid_event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error']['code'] == 'INVALID_AMOUNT'
    
    def test_balance_update_with_correct_values(self, valid_purchase_event, mock_db_client, mock_green_member):
        """Test that balance update is called with correct star delta and annual delta."""
        # Arrange
        valid_purchase_event['data']['membership_id'] = mock_green_member.membership_id
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.get_member.return_value = mock_green_member
        mock_db_client.update_member_balance.return_value = True
        mock_db_client.create_star_ledger_entry.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        response = handler(valid_purchase_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        
        # Verify balance update call
        mock_db_client.update_member_balance.assert_called_once()
        call_args = mock_db_client.update_member_balance.call_args
        assert call_args.kwargs['membership_id'] == mock_green_member.membership_id
        assert call_args.kwargs['star_delta'] == 10
        assert call_args.kwargs['annual_star_delta'] == 10
        assert call_args.kwargs['last_activity'] is not None
    
    def test_last_qualifying_activity_updated(self, valid_purchase_event, mock_db_client, mock_green_member):
        """Test that last qualifying activity timestamp is updated."""
        # Arrange
        valid_purchase_event['data']['membership_id'] = mock_green_member.membership_id
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.get_member.return_value = mock_green_member
        mock_db_client.update_member_balance.return_value = True
        mock_db_client.create_star_ledger_entry.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        before_purchase = datetime.utcnow()
        
        # Act
        response = handler(valid_purchase_event, None)
        
        after_purchase = datetime.utcnow()
        
        # Assert
        assert response['statusCode'] == 200
        
        # Verify last_activity timestamp
        call_args = mock_db_client.update_member_balance.call_args
        last_activity = call_args.kwargs['last_activity']
        assert before_purchase <= last_activity <= after_purchase
    
    def test_transaction_recorded_correctly(self, valid_purchase_event, mock_db_client, mock_green_member):
        """Test that purchase transaction is recorded with correct details."""
        # Arrange
        valid_purchase_event['data']['membership_id'] = mock_green_member.membership_id
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.get_member.return_value = mock_green_member
        mock_db_client.update_member_balance.return_value = True
        mock_db_client.create_star_ledger_entry.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        response = handler(valid_purchase_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        
        # Verify transaction recorded
        mock_db_client.record_transaction.assert_called_once()
        recorded_txn = mock_db_client.record_transaction.call_args[0][0]
        assert isinstance(recorded_txn, Transaction)
        assert recorded_txn.transaction_id == valid_purchase_event['transaction_id']
        assert recorded_txn.membership_id == mock_green_member.membership_id
        assert recorded_txn.type == TransactionType.PURCHASE
        assert recorded_txn.stars_earned == 10
        assert recorded_txn.purchase_amount == Decimal('10.00')
        assert 'Purchase' in recorded_txn.description
    
    def test_star_ledger_entry_for_green_member(self, valid_purchase_event, mock_db_client, mock_green_member):
        """Test that star ledger entry is created for Green tier members."""
        # Arrange
        valid_purchase_event['data']['membership_id'] = mock_green_member.membership_id
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.get_member.return_value = mock_green_member
        mock_db_client.update_member_balance.return_value = True
        mock_db_client.create_star_ledger_entry.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        response = handler(valid_purchase_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        
        # Verify star ledger entry created
        mock_db_client.create_star_ledger_entry.assert_called_once()
        ledger_entry = mock_db_client.create_star_ledger_entry.call_args[0][0]
        assert ledger_entry.membership_id == mock_green_member.membership_id
        assert ledger_entry.star_count == 10
        assert ledger_entry.batch_id is not None
        assert isinstance(ledger_entry.earned_date, datetime)
    
    def test_no_star_ledger_for_gold_member(self, valid_purchase_event, mock_db_client, mock_gold_member):
        """Test that star ledger entry is NOT created for Gold tier members."""
        # Arrange
        valid_purchase_event['data']['membership_id'] = mock_gold_member.membership_id
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.get_member.return_value = mock_gold_member
        mock_db_client.update_member_balance.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        response = handler(valid_purchase_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        mock_db_client.create_star_ledger_entry.assert_not_called()
    
    def test_no_star_ledger_for_reserve_member(self, valid_purchase_event, mock_db_client, mock_reserve_member):
        """Test that star ledger entry is NOT created for Reserve tier members."""
        # Arrange
        valid_purchase_event['data']['membership_id'] = mock_reserve_member.membership_id
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.get_member.return_value = mock_reserve_member
        mock_db_client.update_member_balance.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        response = handler(valid_purchase_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        mock_db_client.create_star_ledger_entry.assert_not_called()
    
    def test_database_error_handling(self, valid_purchase_event, mock_db_client, mock_green_member):
        """Test handling of database errors."""
        # Arrange
        valid_purchase_event['data']['membership_id'] = mock_green_member.membership_id
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.get_member.return_value = mock_green_member
        mock_db_client.update_member_balance.side_effect = Exception("Database connection failed")
        
        # Act
        response = handler(valid_purchase_event, None)
        
        # Assert
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert body['error']['code'] == 'INTERNAL_ERROR'
    
    def test_large_purchase_amount(self, valid_purchase_event, mock_db_client, mock_reserve_member):
        """Test purchase with large amount calculates stars correctly."""
        # Arrange
        valid_purchase_event['data']['membership_id'] = mock_reserve_member.membership_id
        valid_purchase_event['data']['amount'] = '500.00'
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.get_member.return_value = mock_reserve_member
        mock_db_client.update_member_balance.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        response = handler(valid_purchase_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['starsEarned'] == 850  # $500 * 1.7 = 850 stars
    
    def test_small_purchase_amount(self, valid_purchase_event, mock_db_client, mock_green_member):
        """Test purchase with small amount rounds down correctly."""
        # Arrange
        valid_purchase_event['data']['membership_id'] = mock_green_member.membership_id
        valid_purchase_event['data']['amount'] = '0.50'
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.get_member.return_value = mock_green_member
        mock_db_client.update_member_balance.return_value = True
        mock_db_client.create_star_ledger_entry.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        response = handler(valid_purchase_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['starsEarned'] == 0  # $0.50 * 1.0 = 0.5, rounds down to 0
    
    def test_annual_star_count_updated(self, valid_purchase_event, mock_db_client, mock_green_member):
        """Test that annual star count is incremented correctly."""
        # Arrange
        valid_purchase_event['data']['membership_id'] = mock_green_member.membership_id
        mock_db_client.check_transaction_exists.return_value = None
        mock_db_client.get_member.return_value = mock_green_member
        mock_db_client.update_member_balance.return_value = True
        mock_db_client.create_star_ledger_entry.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        response = handler(valid_purchase_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        
        # Verify annual star count updated
        call_args = mock_db_client.update_member_balance.call_args
        assert call_args.kwargs['annual_star_delta'] == 10
