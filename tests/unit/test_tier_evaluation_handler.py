"""Unit tests for tier evaluation handler."""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from decimal import Decimal

# Add the lambda directory to the path for imports
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../lambda'))

from tier_evaluation.handler import (
    handler,
    _calculate_annual_stars,
    _determine_tier_from_stars,
    _remove_star_expiration_dates
)
from common.models import Tier, Transaction, TransactionType, MemberProfile


class TestTierEvaluationHandler:
    """Test cases for the tier evaluation handler."""

    def test_handler_success(self):
        """Test successful tier evaluation execution."""
        # Arrange
        with patch('common.dynamodb.DynamoDBClient') as mock_db_client_class:
            mock_db_client = Mock()
            mock_db_client_class.return_value = mock_db_client
            
            # Mock member data
            mock_member = MemberProfile(
                membership_id="test-member-1",
                email="test@example.com",
                name="Test User",
                phone="555-0123",
                tier=Tier.GREEN,
                star_balance=100,
                annual_star_count=0,
                enrollment_date=datetime.utcnow() - timedelta(days=400),
                tier_since=datetime.utcnow() - timedelta(days=400),
                next_tier_evaluation=datetime.utcnow() - timedelta(days=1)  # Due for evaluation
            )
            
            mock_db_client.query_members_by_tier.return_value = [mock_member]
            mock_db_client.get_member_transactions.return_value = ([], None)
            
            event = {}
            context = Mock()
            
            # Act - handler uses @with_structured_logging decorator, so only needs event and context
            result = handler(event, context)
            
            # Assert
            assert result['statusCode'] == 200
            assert 'evaluations_processed' in result['body']


class TestCalculateAnnualStars:
    """Test cases for annual star calculation."""

    def test_calculate_annual_stars_with_recent_purchases(self):
        """Test calculating annual stars with recent purchase transactions."""
        # Arrange
        mock_db_client = Mock()
        mock_logger = Mock()
        membership_id = "test-member"
        current_time = datetime.utcnow()
        
        # Mock transactions within the past 12 months
        recent_transaction = Transaction(
            transaction_id="txn-1",
            membership_id=membership_id,
            type=TransactionType.PURCHASE,
            timestamp=current_time - timedelta(days=30),
            stars_earned=100
        )
        
        mock_db_client.get_member_transactions.return_value = ([recent_transaction], None)
        
        # Act
        result = _calculate_annual_stars(mock_db_client, membership_id, current_time, mock_logger)
        
        # Assert
        assert result == 100

    def test_calculate_annual_stars_excludes_old_transactions(self):
        """Test that transactions older than 12 months are excluded."""
        # Arrange
        mock_db_client = Mock()
        mock_logger = Mock()
        membership_id = "test-member"
        current_time = datetime.utcnow()
        
        # Mock old transaction (over 12 months ago)
        old_transaction = Transaction(
            transaction_id="txn-1",
            membership_id=membership_id,
            type=TransactionType.PURCHASE,
            timestamp=current_time - timedelta(days=400),
            stars_earned=100
        )
        
        mock_db_client.get_member_transactions.return_value = ([old_transaction], None)
        
        # Act
        result = _calculate_annual_stars(mock_db_client, membership_id, current_time, mock_logger)
        
        # Assert
        assert result == 0


class TestDetermineTierFromStars:
    """Test cases for tier determination logic."""

    def test_determine_tier_reserve(self):
        """Test tier determination for Reserve level (2500+ stars)."""
        assert _determine_tier_from_stars(2500) == Tier.RESERVE
        assert _determine_tier_from_stars(3000) == Tier.RESERVE

    def test_determine_tier_gold(self):
        """Test tier determination for Gold level (500-2499 stars)."""
        assert _determine_tier_from_stars(500) == Tier.GOLD
        assert _determine_tier_from_stars(1000) == Tier.GOLD
        assert _determine_tier_from_stars(2499) == Tier.GOLD

    def test_determine_tier_green(self):
        """Test tier determination for Green level (0-499 stars)."""
        assert _determine_tier_from_stars(0) == Tier.GREEN
        assert _determine_tier_from_stars(100) == Tier.GREEN
        assert _determine_tier_from_stars(499) == Tier.GREEN


class TestRemoveStarExpirationDates:
    """Test cases for removing star expiration dates."""

    @patch('common.logger.StructuredLogger')
    def test_remove_star_expiration_dates_success(self, mock_logger_class):
        """Test successful removal of star expiration dates."""
        # Arrange
        mock_db_client = Mock()
        mock_logger = Mock()
        mock_logger_class.return_value = mock_logger
        membership_id = "test-member"
        
        # Mock star ledger entries
        from common.models import StarLedgerEntry
        star_entry = StarLedgerEntry(
            membership_id=membership_id,
            earned_date=datetime.utcnow() - timedelta(days=30),
            star_count=50,
            expiration_date=datetime.utcnow() + timedelta(days=150),
            batch_id="batch-1"
        )
        
        mock_db_client.get_star_ledger_entries.return_value = [star_entry]
        mock_db_client.table = Mock()
        
        # Act
        _remove_star_expiration_dates(mock_db_client, membership_id, mock_logger)
        
        # Assert
        mock_db_client.get_star_ledger_entries.assert_called_once_with(membership_id)
        mock_db_client.table.update_item.assert_called_once()

    @patch('common.logger.StructuredLogger')
    def test_remove_star_expiration_dates_no_entries(self, mock_logger_class):
        """Test handling when no star ledger entries exist."""
        # Arrange
        mock_db_client = Mock()
        mock_logger = Mock()
        mock_logger_class.return_value = mock_logger
        membership_id = "test-member"
        
        mock_db_client.get_star_ledger_entries.return_value = []
        
        # Act
        _remove_star_expiration_dates(mock_db_client, membership_id, mock_logger)
        
        # Assert
        mock_db_client.get_star_ledger_entries.assert_called_once_with(membership_id)
        # Should not call update_item if no entries
        assert not hasattr(mock_db_client, 'table') or not mock_db_client.table.update_item.called


if __name__ == "__main__":
    pytest.main([__file__])