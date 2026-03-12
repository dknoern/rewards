"""Unit tests for idempotency functionality."""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from moto import mock_aws
import boto3

from common.dynamodb import DynamoDBClient
from common.models import (
    MemberProfile,
    Transaction,
    Tier,
    TransactionType
)


@pytest.fixture
def dynamodb_table():
    """Create a mock DynamoDB table for testing."""
    with mock_aws():
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        
        # Create table with GSIs and TTL
        table = dynamodb.create_table(
            TableName='rewards-program-test',
            KeySchema=[
                {'AttributeName': 'PK', 'KeyType': 'HASH'},
                {'AttributeName': 'SK', 'KeyType': 'RANGE'}
            ],
            AttributeDefinitions=[
                {'AttributeName': 'PK', 'AttributeType': 'S'},
                {'AttributeName': 'SK', 'AttributeType': 'S'},
                {'AttributeName': 'GSI1PK', 'AttributeType': 'S'},
                {'AttributeName': 'GSI1SK', 'AttributeType': 'S'},
                {'AttributeName': 'GSI2PK', 'AttributeType': 'S'},
                {'AttributeName': 'GSI2SK', 'AttributeType': 'S'}
            ],
            GlobalSecondaryIndexes=[
                {
                    'IndexName': 'GSI1',
                    'KeySchema': [
                        {'AttributeName': 'GSI1PK', 'KeyType': 'HASH'},
                        {'AttributeName': 'GSI1SK', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {
                        'ReadCapacityUnits': 5,
                        'WriteCapacityUnits': 5
                    }
                },
                {
                    'IndexName': 'GSI2',
                    'KeySchema': [
                        {'AttributeName': 'GSI2PK', 'KeyType': 'HASH'},
                        {'AttributeName': 'GSI2SK', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {
                        'ReadCapacityUnits': 5,
                        'WriteCapacityUnits': 5
                    }
                }
            ],
            BillingMode='PROVISIONED',
            ProvisionedThroughput={
                'ReadCapacityUnits': 5,
                'WriteCapacityUnits': 5
            }
        )
        
        yield table


@pytest.fixture
def db_client(dynamodb_table):
    """Create DynamoDB client with test table."""
    return DynamoDBClient(table_name='rewards-program-test')


@pytest.fixture
def sample_member():
    """Create a sample member profile."""
    now = datetime.now()
    return MemberProfile(
        membership_id='test-member-123',
        email='test@example.com',
        name='Test User',
        phone='+1234567890',
        tier=Tier.GREEN,
        star_balance=100,
        annual_star_count=50,
        enrollment_date=now,
        tier_since=now,
        next_tier_evaluation=now + timedelta(days=365)
    )


class TestIdempotencyChecker:
    """Tests for idempotency checking functionality (Requirements 10.1-10.4)."""
    
    def test_check_transaction_exists_returns_none_for_new_transaction(self, db_client):
        """
        Test that checking a non-existent transaction ID returns None.
        Validates: Requirement 10.1 - Check for unique transaction identifier
        """
        # Act
        result = db_client.check_transaction_exists('new-txn-123')
        
        # Assert
        assert result is None
    
    def test_check_transaction_exists_returns_data_for_existing_transaction(
        self, db_client, sample_member
    ):
        """
        Test that checking an existing transaction ID returns the original transaction data.
        Validates: Requirement 10.2 - Return original transaction result without reprocessing
        """
        # Arrange
        db_client.create_member(sample_member)
        transaction = Transaction(
            transaction_id='duplicate-txn-456',
            membership_id=sample_member.membership_id,
            type=TransactionType.PURCHASE,
            timestamp=datetime.now(),
            stars_earned=50,
            purchase_amount=Decimal('25.00')
        )
        db_client.record_transaction(transaction)
        
        # Act
        result = db_client.check_transaction_exists('duplicate-txn-456')
        
        # Assert
        assert result is not None
        assert result['transactionId'] == 'duplicate-txn-456'
        assert result['type'] == TransactionType.PURCHASE.value
        assert result['starsEarned'] == 50
    
    def test_transaction_record_includes_ttl_attribute(self, db_client, sample_member):
        """
        Test that recorded transactions include TTL attribute for 30-day cleanup.
        Validates: Requirement 10.4 - Maintain transaction identifiers for at least 30 days
        """
        # Arrange
        db_client.create_member(sample_member)
        now = datetime.now()
        transaction = Transaction(
            transaction_id='ttl-test-txn',
            membership_id=sample_member.membership_id,
            type=TransactionType.PURCHASE,
            timestamp=now,
            stars_earned=25
        )
        
        # Act
        db_client.record_transaction(transaction)
        result = db_client.check_transaction_exists('ttl-test-txn')
        
        # Assert
        assert result is not None
        assert 'ttl' in result
        
        # TTL should be approximately 30 days from now (in epoch seconds)
        expected_ttl = int(now.timestamp() + 30 * 24 * 60 * 60)
        actual_ttl = result['ttl']
        
        # Allow 1 second tolerance for test execution time
        assert abs(actual_ttl - expected_ttl) <= 1
    
    def test_ttl_value_is_30_days_in_future(self, db_client, sample_member):
        """
        Test that TTL is set to exactly 30 days from transaction timestamp.
        Validates: Requirement 10.4 - 30-day retention period
        """
        # Arrange
        db_client.create_member(sample_member)
        transaction_time = datetime(2024, 1, 1, 12, 0, 0)
        transaction = Transaction(
            transaction_id='ttl-exact-test',
            membership_id=sample_member.membership_id,
            type=TransactionType.REDEMPTION,
            timestamp=transaction_time,
            stars_redeemed=60
        )
        
        # Act
        db_client.record_transaction(transaction)
        result = db_client.check_transaction_exists('ttl-exact-test')
        
        # Assert
        expected_ttl = int(transaction_time.timestamp() + 30 * 24 * 60 * 60)
        assert result['ttl'] == expected_ttl
    
    def test_idempotency_check_with_purchase_transaction(self, db_client, sample_member):
        """
        Test idempotency check returns complete purchase transaction data.
        Validates: Requirement 10.2 - Return original transaction result
        """
        # Arrange
        db_client.create_member(sample_member)
        transaction = Transaction(
            transaction_id='purchase-idem-test',
            membership_id=sample_member.membership_id,
            type=TransactionType.PURCHASE,
            timestamp=datetime.now(),
            stars_earned=100,
            purchase_amount=Decimal('50.00'),
            description='Test purchase'
        )
        db_client.record_transaction(transaction)
        
        # Act
        result = db_client.check_transaction_exists('purchase-idem-test')
        
        # Assert
        assert result is not None
        assert result['transactionId'] == 'purchase-idem-test'
        assert result['type'] == TransactionType.PURCHASE.value
        assert result['starsEarned'] == 100
        assert float(result['purchaseAmount']) == 50.00
        assert result['description'] == 'Test purchase'
    
    def test_idempotency_check_with_redemption_transaction(self, db_client, sample_member):
        """
        Test idempotency check returns complete redemption transaction data.
        Validates: Requirement 10.2 - Return original transaction result
        """
        # Arrange
        db_client.create_member(sample_member)
        transaction = Transaction(
            transaction_id='redemption-idem-test',
            membership_id=sample_member.membership_id,
            type=TransactionType.REDEMPTION,
            timestamp=datetime.now(),
            stars_redeemed=60,
            description='Free coffee'
        )
        db_client.record_transaction(transaction)
        
        # Act
        result = db_client.check_transaction_exists('redemption-idem-test')
        
        # Assert
        assert result is not None
        assert result['transactionId'] == 'redemption-idem-test'
        assert result['type'] == TransactionType.REDEMPTION.value
        assert result['starsRedeemed'] == 60
        assert result['description'] == 'Free coffee'
    
    def test_multiple_transactions_same_member_different_ids(self, db_client, sample_member):
        """
        Test that multiple transactions for the same member with different IDs are all stored.
        Validates: Requirement 10.1 - Unique transaction identifier checking
        """
        # Arrange
        db_client.create_member(sample_member)
        
        # Create multiple transactions with different IDs
        for i in range(3):
            transaction = Transaction(
                transaction_id=f'multi-txn-{i}',
                membership_id=sample_member.membership_id,
                type=TransactionType.PURCHASE,
                timestamp=datetime.now() + timedelta(seconds=i),
                stars_earned=10 * (i + 1)
            )
            db_client.record_transaction(transaction)
        
        # Act & Assert - Each transaction should be retrievable
        for i in range(3):
            result = db_client.check_transaction_exists(f'multi-txn-{i}')
            assert result is not None
            assert result['transactionId'] == f'multi-txn-{i}'
            assert result['starsEarned'] == 10 * (i + 1)
    
    def test_gsi2_query_returns_only_one_result(self, db_client, sample_member):
        """
        Test that GSI2 query with Limit=1 returns only the first matching transaction.
        Validates: Requirement 10.1 - Efficient transaction ID lookup
        """
        # Arrange
        db_client.create_member(sample_member)
        transaction = Transaction(
            transaction_id='single-result-test',
            membership_id=sample_member.membership_id,
            type=TransactionType.PURCHASE,
            timestamp=datetime.now(),
            stars_earned=75
        )
        db_client.record_transaction(transaction)
        
        # Act
        result = db_client.check_transaction_exists('single-result-test')
        
        # Assert
        assert result is not None
        # Verify it's a single dict, not a list
        assert isinstance(result, dict)
        assert result['transactionId'] == 'single-result-test'
    
    def test_transaction_includes_gsi2_keys(self, db_client, sample_member):
        """
        Test that recorded transactions include GSI2PK and GSI2SK for idempotency lookups.
        Validates: Requirement 10.1 - Transaction identifier indexing
        """
        # Arrange
        db_client.create_member(sample_member)
        timestamp = datetime.now()
        transaction = Transaction(
            transaction_id='gsi2-keys-test',
            membership_id=sample_member.membership_id,
            type=TransactionType.PURCHASE,
            timestamp=timestamp,
            stars_earned=30
        )
        
        # Act
        db_client.record_transaction(transaction)
        result = db_client.check_transaction_exists('gsi2-keys-test')
        
        # Assert
        assert result is not None
        assert result['GSI2PK'] == 'TXN#gsi2-keys-test'
        assert result['GSI2SK'] == timestamp.isoformat()
    
    def test_check_transaction_extracts_membership_id(self, db_client, sample_member):
        """
        Test that check_transaction_exists extracts membershipId from PK for convenience.
        Validates: Requirement 10.2 - Return original transaction result with member context
        """
        # Arrange
        db_client.create_member(sample_member)
        transaction = Transaction(
            transaction_id='extract-member-test',
            membership_id=sample_member.membership_id,
            type=TransactionType.PURCHASE,
            timestamp=datetime.now(),
            stars_earned=45
        )
        db_client.record_transaction(transaction)
        
        # Act
        result = db_client.check_transaction_exists('extract-member-test')
        
        # Assert
        assert result is not None
        assert 'membershipId' in result
        assert result['membershipId'] == sample_member.membership_id
        # Original PK should still be present
        assert result['PK'] == f'MEMBER#{sample_member.membership_id}'


class TestIdempotencyIntegration:
    """Integration tests for idempotency in transaction processing."""
    
    def test_duplicate_transaction_does_not_modify_balance(self, db_client, sample_member):
        """
        Test that processing a duplicate transaction ID does not modify member balance.
        Validates: Requirement 10.3 - Don't modify member's star balance for duplicates
        
        Note: This test verifies the idempotency check mechanism. The actual handler
        logic that uses this check to prevent duplicate processing is tested in handler tests.
        """
        # Arrange
        db_client.create_member(sample_member)
        initial_balance = sample_member.star_balance
        
        # Record first transaction
        transaction = Transaction(
            transaction_id='duplicate-balance-test',
            membership_id=sample_member.membership_id,
            type=TransactionType.PURCHASE,
            timestamp=datetime.now(),
            stars_earned=50
        )
        db_client.record_transaction(transaction)
        db_client.update_member_balance(sample_member.membership_id, star_delta=50)
        
        # Act - Check if transaction exists (simulating duplicate detection)
        duplicate_check = db_client.check_transaction_exists('duplicate-balance-test')
        
        # Assert - Transaction exists, so handler should not process again
        assert duplicate_check is not None
        
        # Verify balance was only updated once
        member = db_client.get_member(sample_member.membership_id)
        assert member.star_balance == initial_balance + 50
    
    def test_idempotency_check_before_transaction_processing(self, db_client, sample_member):
        """
        Test the recommended flow: check idempotency before processing transaction.
        Validates: Requirements 10.1, 10.2 - Check and return cached result
        """
        # Arrange
        db_client.create_member(sample_member)
        transaction_id = 'flow-test-txn'
        
        # First request - transaction doesn't exist
        first_check = db_client.check_transaction_exists(transaction_id)
        assert first_check is None
        
        # Process transaction
        transaction = Transaction(
            transaction_id=transaction_id,
            membership_id=sample_member.membership_id,
            type=TransactionType.PURCHASE,
            timestamp=datetime.now(),
            stars_earned=40
        )
        db_client.record_transaction(transaction)
        db_client.update_member_balance(sample_member.membership_id, star_delta=40)
        
        # Second request - transaction exists (duplicate)
        second_check = db_client.check_transaction_exists(transaction_id)
        assert second_check is not None
        assert second_check['transactionId'] == transaction_id
        
        # Handler should return cached result without reprocessing
        # Verify balance was only updated once
        member = db_client.get_member(sample_member.membership_id)
        assert member.star_balance == 140  # 100 initial + 40 from single processing
