"""Integration test for tier evaluation handler."""

import pytest
import sys
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch

# Add the lambda directory to the path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../lambda'))

from tier_evaluation.handler import handler
from common.models import Tier, MemberProfile


class TestTierEvaluationIntegration:
    """Integration tests for tier evaluation handler."""

    @patch.dict(os.environ, {'TABLE_NAME': 'test-table'})
    @patch('common.dynamodb.DynamoDBClient')
    def test_tier_evaluation_end_to_end(self, mock_db_client_class):
        """Test complete tier evaluation flow."""
        # Arrange
        mock_db_client = Mock()
        mock_db_client_class.return_value = mock_db_client
        
        # Mock member due for evaluation (Green tier with 600 stars earned)
        mock_member = MemberProfile(
            membership_id="test-member-1",
            email="test@example.com",
            name="Test User",
            phone="555-0123",
            tier=Tier.GREEN,
            star_balance=600,
            annual_star_count=0,  # Will be recalculated
            enrollment_date=datetime.utcnow() - timedelta(days=400),
            tier_since=datetime.utcnow() - timedelta(days=400),
            next_tier_evaluation=datetime.utcnow() - timedelta(days=1)  # Due for evaluation
        )
        
        # Mock transactions showing 600 stars earned in past 12 months
        from common.models import Transaction, TransactionType
        mock_transactions = [
            Transaction(
                transaction_id="txn-1",
                membership_id="test-member-1",
                type=TransactionType.PURCHASE,
                timestamp=datetime.utcnow() - timedelta(days=30),
                stars_earned=300
            ),
            Transaction(
                transaction_id="txn-2", 
                membership_id="test-member-1",
                type=TransactionType.PURCHASE,
                timestamp=datetime.utcnow() - timedelta(days=60),
                stars_earned=300
            )
        ]
        
        # Configure mocks
        mock_db_client.query_members_by_tier.side_effect = [
            [mock_member],  # Green tier members
            [],  # Gold tier members
            []   # Reserve tier members
        ]
        mock_db_client.get_member_transactions.return_value = (mock_transactions, None)
        mock_db_client.get_star_ledger_entries.return_value = []
        
        event = {}
        context = Mock()
        
        # Act
        result = handler(event, context)
        
        # Assert
        assert result['statusCode'] == 200
        
        # Verify member was promoted to Gold (600 stars >= 500)
        mock_db_client.update_member_tier.assert_called()
        call_args = mock_db_client.update_member_tier.call_args
        assert call_args[1]['new_tier'] == Tier.GOLD
        
        # Verify transaction was recorded
        mock_db_client.record_transaction.assert_called()
        
        print("Integration test passed - member promoted from Green to Gold!")


if __name__ == "__main__":
    pytest.main([__file__])