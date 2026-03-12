"""Unit tests for DynamoDB access layer."""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from moto import mock_aws
import boto3
from botocore.exceptions import ClientError

from common.dynamodb import DynamoDBClient
from common.models import (
    MemberProfile,
    Transaction,
    StarLedgerEntry,
    Tier,
    TransactionType
)


@pytest.fixture
def dynamodb_table():
    """Create a mock DynamoDB table for testing."""
    with mock_aws():
        dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
        
        # Create table with GSIs
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


class TestGetMember:
    """Tests for get_member method."""
    
    def test_get_existing_member(self, db_client, sample_member):
        """Test retrieving an existing member returns correct data."""
        # Arrange
        db_client.create_member(sample_member)
        
        # Act
        result = db_client.get_member(sample_member.membership_id)
        
        # Assert
        assert result is not None
        assert result.membership_id == sample_member.membership_id
        assert result.email == sample_member.email
        assert result.tier == Tier.GREEN
        assert result.star_balance == 100
    
    def test_get_nonexistent_member(self, db_client):
        """Test retrieving non-existent member returns None."""
        # Act
        result = db_client.get_member('nonexistent-id')
        
        # Assert
        assert result is None


class TestCreateMember:
    """Tests for create_member method."""
    
    def test_create_new_member(self, db_client, sample_member):
        """Test creating a new member succeeds."""
        # Act
        result = db_client.create_member(sample_member)
        
        # Assert
        assert result is True
        retrieved = db_client.get_member(sample_member.membership_id)
        assert retrieved is not None
        assert retrieved.membership_id == sample_member.membership_id
    
    def test_create_duplicate_member_raises_error(self, db_client, sample_member):
        """Test creating duplicate member raises ValueError."""
        # Arrange
        db_client.create_member(sample_member)
        
        # Act & Assert
        with pytest.raises(ValueError, match="already exists"):
            db_client.create_member(sample_member)


class TestUpdateMemberBalance:
    """Tests for update_member_balance method."""
    
    def test_increase_balance(self, db_client, sample_member):
        """Test increasing star balance updates correctly."""
        # Arrange
        db_client.create_member(sample_member)
        
        # Act
        result = db_client.update_member_balance(
            sample_member.membership_id,
            star_delta=50,
            annual_star_delta=50
        )
        
        # Assert
        assert result is True
        updated = db_client.get_member(sample_member.membership_id)
        assert updated.star_balance == 150
        assert updated.annual_star_count == 100
    
    def test_decrease_balance(self, db_client, sample_member):
        """Test decreasing star balance updates correctly."""
        # Arrange
        db_client.create_member(sample_member)
        
        # Act
        result = db_client.update_member_balance(
            sample_member.membership_id,
            star_delta=-30
        )
        
        # Assert
        assert result is True
        updated = db_client.get_member(sample_member.membership_id)
        assert updated.star_balance == 70
    
    def test_insufficient_balance_raises_error(self, db_client, sample_member):
        """Test attempting to reduce balance below zero raises ValueError."""
        # Arrange
        db_client.create_member(sample_member)
        
        # Act & Assert
        with pytest.raises(ValueError, match="Insufficient star balance"):
            db_client.update_member_balance(
                sample_member.membership_id,
                star_delta=-150
            )
    
    def test_update_with_last_activity(self, db_client, sample_member):
        """Test updating balance with last activity timestamp."""
        # Arrange
        db_client.create_member(sample_member)
        new_activity = datetime.now()
        
        # Act
        db_client.update_member_balance(
            sample_member.membership_id,
            star_delta=25,
            last_activity=new_activity
        )
        
        # Assert
        updated = db_client.get_member(sample_member.membership_id)
        assert updated.last_qualifying_activity is not None
        assert updated.last_qualifying_activity.replace(microsecond=0) == \
               new_activity.replace(microsecond=0)


class TestRecordTransaction:
    """Tests for record_transaction method."""
    
    def test_record_purchase_transaction(self, db_client, sample_member):
        """Test recording a purchase transaction."""
        # Arrange
        db_client.create_member(sample_member)
        transaction = Transaction(
            transaction_id='txn-123',
            membership_id=sample_member.membership_id,
            type=TransactionType.PURCHASE,
            timestamp=datetime.now(),
            stars_earned=50,
            purchase_amount=Decimal('25.00')
        )
        
        # Act
        result = db_client.record_transaction(transaction)
        
        # Assert
        assert result is True
    
    def test_record_redemption_transaction(self, db_client, sample_member):
        """Test recording a redemption transaction."""
        # Arrange
        db_client.create_member(sample_member)
        transaction = Transaction(
            transaction_id='txn-456',
            membership_id=sample_member.membership_id,
            type=TransactionType.REDEMPTION,
            timestamp=datetime.now(),
            stars_redeemed=60,
            description='Free coffee'
        )
        
        # Act
        result = db_client.record_transaction(transaction)
        
        # Assert
        assert result is True


class TestCheckTransactionExists:
    """Tests for check_transaction_exists method (idempotency)."""
    
    def test_existing_transaction_found(self, db_client, sample_member):
        """Test checking for existing transaction returns transaction data."""
        # Arrange
        db_client.create_member(sample_member)
        transaction = Transaction(
            transaction_id='txn-789',
            membership_id=sample_member.membership_id,
            type=TransactionType.PURCHASE,
            timestamp=datetime.now(),
            stars_earned=25
        )
        db_client.record_transaction(transaction)
        
        # Act
        result = db_client.check_transaction_exists('txn-789')
        
        # Assert
        assert result is not None
        assert result['transactionId'] == 'txn-789'
    
    def test_nonexistent_transaction_returns_none(self, db_client):
        """Test checking for non-existent transaction returns None."""
        # Act
        result = db_client.check_transaction_exists('nonexistent-txn')
        
        # Assert
        assert result is None


class TestGetMemberTransactions:
    """Tests for get_member_transactions method."""
    
    def test_get_transactions_returns_list(self, db_client, sample_member):
        """Test retrieving transaction history returns transactions."""
        # Arrange
        db_client.create_member(sample_member)
        
        # Create multiple transactions
        for i in range(3):
            transaction = Transaction(
                transaction_id=f'txn-{i}',
                membership_id=sample_member.membership_id,
                type=TransactionType.PURCHASE,
                timestamp=datetime.now() + timedelta(seconds=i),
                stars_earned=10 * (i + 1)
            )
            db_client.record_transaction(transaction)
        
        # Act
        transactions, next_key = db_client.get_member_transactions(
            sample_member.membership_id
        )
        
        # Assert
        assert len(transactions) == 3
        assert all(isinstance(t, Transaction) for t in transactions)
        # Should be in reverse chronological order (most recent first)
        assert transactions[0].stars_earned == 30
    
    def test_get_transactions_with_pagination(self, db_client, sample_member):
        """Test transaction retrieval respects limit parameter."""
        # Arrange
        db_client.create_member(sample_member)
        
        for i in range(5):
            transaction = Transaction(
                transaction_id=f'txn-{i}',
                membership_id=sample_member.membership_id,
                type=TransactionType.PURCHASE,
                timestamp=datetime.now() + timedelta(seconds=i),
                stars_earned=10
            )
            db_client.record_transaction(transaction)
        
        # Act
        transactions, next_key = db_client.get_member_transactions(
            sample_member.membership_id,
            limit=2
        )
        
        # Assert
        assert len(transactions) == 2
        assert next_key is not None


class TestStarLedgerOperations:
    """Tests for star ledger entry operations."""
    
    def test_create_star_ledger_entry(self, db_client, sample_member):
        """Test creating a star ledger entry."""
        # Arrange
        db_client.create_member(sample_member)
        entry = StarLedgerEntry(
            membership_id=sample_member.membership_id,
            earned_date=datetime.now(),
            star_count=50,
            expiration_date=datetime.now() + timedelta(days=180),
            batch_id='batch-123'
        )
        
        # Act
        result = db_client.create_star_ledger_entry(entry)
        
        # Assert
        assert result is True
    
    def test_get_star_ledger_entries(self, db_client, sample_member):
        """Test retrieving star ledger entries."""
        # Arrange
        db_client.create_member(sample_member)
        
        for i in range(3):
            entry = StarLedgerEntry(
                membership_id=sample_member.membership_id,
                earned_date=datetime.now() + timedelta(days=i),
                star_count=25,
                batch_id=f'batch-{i}'
            )
            db_client.create_star_ledger_entry(entry)
        
        # Act
        entries = db_client.get_star_ledger_entries(sample_member.membership_id)
        
        # Assert
        assert len(entries) == 3
        assert all(isinstance(e, StarLedgerEntry) for e in entries)


class TestQueryMembersByTier:
    """Tests for query_members_by_tier method (GSI1)."""
    
    def test_query_members_by_tier(self, db_client):
        """Test querying members by tier returns correct members."""
        # Arrange
        now = datetime.now()
        for i in range(3):
            member = MemberProfile(
                membership_id=f'member-{i}',
                email=f'test{i}@example.com',
                name=f'Test User {i}',
                phone='+1234567890',
                tier=Tier.GREEN,
                star_balance=100,
                annual_star_count=50,
                enrollment_date=now,
                tier_since=now,
                next_tier_evaluation=now + timedelta(days=365)
            )
            db_client.create_member(member)
        
        # Act
        members = db_client.query_members_by_tier(Tier.GREEN)
        
        # Assert
        assert len(members) == 3
        assert all(m.tier == Tier.GREEN for m in members)
    
    def test_query_members_with_evaluation_filter(self, db_client):
        """Test querying members with evaluation date filter."""
        # Arrange
        now = datetime.now()
        past_eval = now - timedelta(days=10)
        future_eval = now + timedelta(days=365)
        
        # Member with past evaluation date
        member1 = MemberProfile(
            membership_id='member-past',
            email='past@example.com',
            name='Past Member',
            phone='+1234567890',
            tier=Tier.GOLD,
            star_balance=100,
            annual_star_count=500,
            enrollment_date=now - timedelta(days=400),
            tier_since=now - timedelta(days=400),
            next_tier_evaluation=past_eval
        )
        db_client.create_member(member1)
        
        # Member with future evaluation date
        member2 = MemberProfile(
            membership_id='member-future',
            email='future@example.com',
            name='Future Member',
            phone='+1234567890',
            tier=Tier.GOLD,
            star_balance=100,
            annual_star_count=500,
            enrollment_date=now,
            tier_since=now,
            next_tier_evaluation=future_eval
        )
        db_client.create_member(member2)
        
        # Act
        members = db_client.query_members_by_tier(
            Tier.GOLD,
            evaluation_date_before=now
        )
        
        # Assert
        assert len(members) == 1
        assert members[0].membership_id == 'member-past'


class TestUpdateMemberTier:
    """Tests for update_member_tier method."""
    
    def test_update_tier_succeeds(self, db_client, sample_member):
        """Test updating member tier updates all related fields."""
        # Arrange
        db_client.create_member(sample_member)
        new_tier_date = datetime.now()
        next_eval = new_tier_date + timedelta(days=365)
        
        # Act
        result = db_client.update_member_tier(
            sample_member.membership_id,
            Tier.GOLD,
            new_tier_date,
            next_eval
        )
        
        # Assert
        assert result is True
        updated = db_client.get_member(sample_member.membership_id)
        assert updated.tier == Tier.GOLD


class TestUpdateMember:
    """Tests for generic update_member method."""
    
    def test_update_single_field(self, db_client, sample_member):
        """Test updating a single field."""
        # Arrange
        db_client.create_member(sample_member)
        
        # Act
        result = db_client.update_member(
            sample_member.membership_id,
            {'starBalance': 200}
        )
        
        # Assert
        assert result is True
        updated = db_client.get_member(sample_member.membership_id)
        assert updated.star_balance == 200
    
    def test_update_nonexistent_member_raises_error(self, db_client):
        """Test updating non-existent member raises ValueError."""
        # Act & Assert
        with pytest.raises(ValueError, match="not found"):
            db_client.update_member('nonexistent-id', {'starBalance': 100})
    
    def test_update_with_no_updates_raises_error(self, db_client, sample_member):
        """Test calling update with empty dict raises ValueError."""
        # Arrange
        db_client.create_member(sample_member)
        
        # Act & Assert
        with pytest.raises(ValueError, match="No updates provided"):
            db_client.update_member(sample_member.membership_id, {})
