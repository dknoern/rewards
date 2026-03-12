"""Unit tests for expiration handler."""

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import pytest
from expiration.handler import handler, process_star_expiration, process_member_expiration
from common.models import MemberProfile, Tier, StarLedgerEntry


@pytest.fixture
def mock_db_client():
    """Create a mock DynamoDB client."""
    with patch('expiration.handler.DynamoDBClient') as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_green_member_inactive():
    """Create a mock Green tier member with no recent activity."""
    return MemberProfile(
        membership_id=str(uuid.uuid4()),
        email='inactive@example.com',
        name='Inactive User',
        phone='+1234567890',
        tier=Tier.GREEN,
        star_balance=100,
        annual_star_count=50,
        enrollment_date=datetime.utcnow() - timedelta(days=365),
        last_qualifying_activity=datetime.utcnow() - timedelta(days=60),  # 2 months ago
        tier_since=datetime.utcnow() - timedelta(days=365),
        next_tier_evaluation=datetime.utcnow() + timedelta(days=30)
    )


@pytest.fixture
def mock_green_member_active():
    """Create a mock Green tier member with recent activity."""
    return MemberProfile(
        membership_id=str(uuid.uuid4()),
        email='active@example.com',
        name='Active User',
        phone='+1234567890',
        tier=Tier.GREEN,
        star_balance=200,
        annual_star_count=100,
        enrollment_date=datetime.utcnow() - timedelta(days=365),
        last_qualifying_activity=datetime.utcnow() - timedelta(days=15),  # 15 days ago
        tier_since=datetime.utcnow() - timedelta(days=365),
        next_tier_evaluation=datetime.utcnow() + timedelta(days=30)
    )


@pytest.fixture
def mock_expired_star_entries():
    """Create mock star ledger entries that are expired."""
    current_time = datetime.utcnow()
    return [
        StarLedgerEntry(
            membership_id=str(uuid.uuid4()),
            earned_date=current_time - timedelta(days=200),  # 200 days ago (expired)
            star_count=50,
            batch_id=str(uuid.uuid4())
        ),
        StarLedgerEntry(
            membership_id=str(uuid.uuid4()),
            earned_date=current_time - timedelta(days=190),  # 190 days ago (expired)
            star_count=30,
            batch_id=str(uuid.uuid4())
        )
    ]


@pytest.fixture
def mock_valid_star_entries():
    """Create mock star ledger entries that are not expired."""
    current_time = datetime.utcnow()
    return [
        StarLedgerEntry(
            membership_id=str(uuid.uuid4()),
            earned_date=current_time - timedelta(days=100),  # 100 days ago (not expired)
            star_count=40,
            batch_id=str(uuid.uuid4())
        ),
        StarLedgerEntry(
            membership_id=str(uuid.uuid4()),
            earned_date=current_time - timedelta(days=50),  # 50 days ago (not expired)
            star_count=60,
            batch_id=str(uuid.uuid4())
        )
    ]


class TestExpirationHandler:
    """Test cases for expiration handler."""
    
    def test_successful_expiration_processing(self, mock_db_client, mock_green_member_inactive, mock_expired_star_entries):
        """Test successful expiration processing for inactive Green member."""
        # Arrange
        mock_db_client.query_members_by_tier.return_value = [mock_green_member_inactive]
        mock_db_client.get_star_ledger_entries.return_value = mock_expired_star_entries
        mock_db_client.update_member_balance.return_value = True
        mock_db_client.delete_star_ledger_entries.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        response = handler({}, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['message'] == 'Star expiration handler executed successfully'
        assert 'results' in body
        
        # Verify DynamoDB calls
        mock_db_client.query_members_by_tier.assert_called_once_with(Tier.GREEN)
        mock_db_client.get_star_ledger_entries.assert_called_once()
        mock_db_client.update_member_balance.assert_called_once()
        mock_db_client.delete_star_ledger_entries.assert_called_once()
        mock_db_client.record_transaction.assert_called_once()
    
    def test_no_expiration_for_active_member(self, mock_db_client, mock_green_member_active):
        """Test that active Green members don't have stars expired."""
        # Arrange
        mock_db_client.query_members_by_tier.return_value = [mock_green_member_active]
        
        # Act
        response = handler({}, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        results = body['results']
        assert results['membersProcessed'] == 1
        assert results['membersWithExpiration'] == 0
        assert results['totalStarsExpired'] == 0
        
        # Verify no expiration processing occurred
        mock_db_client.get_star_ledger_entries.assert_not_called()
        mock_db_client.update_member_balance.assert_not_called()
    
    def test_no_expiration_for_valid_stars(self, mock_db_client, mock_green_member_inactive, mock_valid_star_entries):
        """Test that non-expired stars are not processed."""
        # Arrange
        mock_db_client.query_members_by_tier.return_value = [mock_green_member_inactive]
        mock_db_client.get_star_ledger_entries.return_value = mock_valid_star_entries
        
        # Act
        response = handler({}, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        results = body['results']
        assert results['membersProcessed'] == 1
        assert results['membersWithExpiration'] == 0
        assert results['totalStarsExpired'] == 0
        
        # Verify no balance update occurred
        mock_db_client.update_member_balance.assert_not_called()
    
    def test_process_member_expiration_with_expired_stars(self, mock_db_client, mock_expired_star_entries):
        """Test processing expiration for a member with expired stars."""
        # Arrange
        membership_id = str(uuid.uuid4())
        current_time = datetime.utcnow()
        mock_db_client.get_star_ledger_entries.return_value = mock_expired_star_entries
        mock_db_client.update_member_balance.return_value = True
        mock_db_client.delete_star_ledger_entries.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        expired_stars = process_member_expiration(mock_db_client, membership_id, current_time, MagicMock())
        
        # Assert
        assert expired_stars == 80  # 50 + 30 stars
        
        # Verify balance update with negative delta
        mock_db_client.update_member_balance.assert_called_once()
        call_args = mock_db_client.update_member_balance.call_args
        assert call_args.kwargs['membership_id'] == membership_id
        assert call_args.kwargs['star_delta'] == -80
        assert call_args.kwargs['annual_star_delta'] == 0
    
    def test_process_member_expiration_no_expired_stars(self, mock_db_client, mock_valid_star_entries):
        """Test processing expiration for a member with no expired stars."""
        # Arrange
        membership_id = str(uuid.uuid4())
        current_time = datetime.utcnow()
        mock_db_client.get_star_ledger_entries.return_value = mock_valid_star_entries
        
        # Act
        expired_stars = process_member_expiration(mock_db_client, membership_id, current_time, MagicMock())
        
        # Assert
        assert expired_stars == 0
        
        # Verify no balance update occurred
        mock_db_client.update_member_balance.assert_not_called()
    
    def test_process_member_expiration_no_star_entries(self, mock_db_client):
        """Test processing expiration for a member with no star ledger entries."""
        # Arrange
        membership_id = str(uuid.uuid4())
        current_time = datetime.utcnow()
        mock_db_client.get_star_ledger_entries.return_value = []
        
        # Act
        expired_stars = process_member_expiration(mock_db_client, membership_id, current_time, MagicMock())
        
        # Assert
        assert expired_stars == 0
        
        # Verify no processing occurred
        mock_db_client.update_member_balance.assert_not_called()
        mock_db_client.delete_star_ledger_entries.assert_not_called()
    
    def test_expiration_transaction_recorded_correctly(self, mock_db_client, mock_green_member_inactive, mock_expired_star_entries):
        """Test that expiration transaction is recorded with correct details."""
        # Arrange
        mock_db_client.query_members_by_tier.return_value = [mock_green_member_inactive]
        mock_db_client.get_star_ledger_entries.return_value = mock_expired_star_entries
        mock_db_client.update_member_balance.return_value = True
        mock_db_client.delete_star_ledger_entries.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        response = handler({}, None)
        
        # Assert
        assert response['statusCode'] == 200
        
        # Verify transaction recorded
        mock_db_client.record_transaction.assert_called_once()
        recorded_txn = mock_db_client.record_transaction.call_args[0][0]
        assert recorded_txn.membership_id == mock_green_member_inactive.membership_id
        assert recorded_txn.type.value == 'expiration'
        assert recorded_txn.stars_redeemed == 80  # Total expired stars
        assert 'Star expiration' in recorded_txn.description
    
    def test_batch_ids_deleted_correctly(self, mock_db_client, mock_green_member_inactive, mock_expired_star_entries):
        """Test that correct batch IDs are deleted from star ledger."""
        # Arrange
        mock_db_client.query_members_by_tier.return_value = [mock_green_member_inactive]
        mock_db_client.get_star_ledger_entries.return_value = mock_expired_star_entries
        mock_db_client.update_member_balance.return_value = True
        mock_db_client.delete_star_ledger_entries.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        expected_batch_ids = [entry.batch_id for entry in mock_expired_star_entries]
        
        # Act
        response = handler({}, None)
        
        # Assert
        assert response['statusCode'] == 200
        
        # Verify correct batch IDs deleted
        mock_db_client.delete_star_ledger_entries.assert_called_once()
        call_args = mock_db_client.delete_star_ledger_entries.call_args
        assert call_args[0][0] == mock_green_member_inactive.membership_id
        assert set(call_args[0][1]) == set(expected_batch_ids)
    
    def test_multiple_members_processing(self, mock_db_client, mock_green_member_inactive, mock_green_member_active, mock_expired_star_entries):
        """Test processing multiple Green members with mixed expiration scenarios."""
        # Arrange
        inactive_member = mock_green_member_inactive
        active_member = mock_green_member_active
        
        mock_db_client.query_members_by_tier.return_value = [inactive_member, active_member]
        
        def get_star_entries_side_effect(membership_id):
            if membership_id == inactive_member.membership_id:
                return mock_expired_star_entries
            else:
                return []  # Active member has no entries or no expired entries
        
        mock_db_client.get_star_ledger_entries.side_effect = get_star_entries_side_effect
        mock_db_client.update_member_balance.return_value = True
        mock_db_client.delete_star_ledger_entries.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        response = handler({}, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        results = body['results']
        assert results['membersProcessed'] == 2
        assert results['membersWithExpiration'] == 1  # Only inactive member
        assert results['totalStarsExpired'] == 80
    
    def test_error_handling(self, mock_db_client):
        """Test error handling when database operations fail."""
        # Arrange
        mock_db_client.query_members_by_tier.side_effect = Exception("Database connection failed")
        
        # Act
        response = handler({}, None)
        
        # Assert
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert body['error'] == 'Internal server error during star expiration'
        assert 'Database connection failed' in body['message']
    
    def test_six_month_expiration_threshold(self, mock_db_client):
        """Test that stars expire exactly at 6 months (180 days)."""
        # Arrange
        membership_id = str(uuid.uuid4())
        current_time = datetime.utcnow()
        
        # Create entries at exactly 180 days and 181 days
        star_entries = [
            StarLedgerEntry(
                membership_id=membership_id,
                earned_date=current_time - timedelta(days=180),  # Exactly 6 months
                star_count=25,
                batch_id=str(uuid.uuid4())
            ),
            StarLedgerEntry(
                membership_id=membership_id,
                earned_date=current_time - timedelta(days=181),  # Over 6 months
                star_count=35,
                batch_id=str(uuid.uuid4())
            ),
            StarLedgerEntry(
                membership_id=membership_id,
                earned_date=current_time - timedelta(days=179),  # Under 6 months
                star_count=40,
                batch_id=str(uuid.uuid4())
            )
        ]
        
        mock_db_client.get_star_ledger_entries.return_value = star_entries
        mock_db_client.update_member_balance.return_value = True
        mock_db_client.delete_star_ledger_entries.return_value = True
        mock_db_client.record_transaction.return_value = True
        
        # Act
        expired_stars = process_member_expiration(mock_db_client, membership_id, current_time, MagicMock())
        
        # Assert
        assert expired_stars == 60  # 25 + 35 stars (180 and 181 days old)
        
        # Verify correct entries were deleted
        call_args = mock_db_client.delete_star_ledger_entries.call_args
        deleted_batch_ids = call_args[0][1]
        assert len(deleted_batch_ids) == 2  # Only 2 entries should be deleted