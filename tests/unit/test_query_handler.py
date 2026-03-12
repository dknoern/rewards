"""Unit tests for query handler."""

import json
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch
import pytest
from query.handler import handler
from common.models import MemberProfile, Tier, Transaction, TransactionType


@pytest.fixture
def valid_api_gateway_event():
    """Create a valid API Gateway event for member query."""
    membership_id = str(uuid.uuid4())
    return {
        'httpMethod': 'GET',
        'path': f'/v1/members/{membership_id}',
        'pathParameters': {
            'membershipId': membership_id
        },
        'headers': {
            'Content-Type': 'application/json'
        }
    }


@pytest.fixture
def mock_db_client():
    """Create a mock DynamoDB client."""
    with patch('query.handler.DynamoDBClient') as mock_class:
        mock_instance = MagicMock()
        mock_class.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def sample_member_profile():
    """Create a sample member profile for testing."""
    now = datetime.utcnow()
    return MemberProfile(
        membership_id=str(uuid.uuid4()),
        email='test@example.com',
        name='Test User',
        phone='+1234567890',
        tier=Tier.GREEN,
        star_balance=150,
        annual_star_count=300,
        enrollment_date=now - timedelta(days=90),
        last_qualifying_activity=now - timedelta(days=5),
        tier_since=now - timedelta(days=90),
        next_tier_evaluation=now + timedelta(days=275)
    )


class TestQueryHandler:
    """Test cases for query handler."""
    
    def test_successful_member_query(self, valid_api_gateway_event, mock_db_client, sample_member_profile):
        """Test successful query of existing member."""
        # Arrange
        mock_db_client.get_member.return_value = sample_member_profile
        
        # Act
        response = handler(valid_api_gateway_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        assert response['headers']['Content-Type'] == 'application/json'
        
        body = json.loads(response['body'])
        assert body['membershipId'] == sample_member_profile.membership_id
        assert body['tier'] == 'Green'
        assert body['starBalance'] == 150
        assert body['annualStarCount'] == 300
        assert body['enrollmentDate'] == sample_member_profile.enrollment_date.isoformat()
        assert body['lastActivity'] == sample_member_profile.last_qualifying_activity.isoformat()
        assert body['tierSince'] == sample_member_profile.tier_since.isoformat()
        
        # Verify DynamoDB was called with correct membership ID
        mock_db_client.get_member.assert_called_once_with(
            valid_api_gateway_event['pathParameters']['membershipId']
        )
    
    def test_member_not_found(self, valid_api_gateway_event, mock_db_client):
        """Test error response when member does not exist."""
        # Arrange
        mock_db_client.get_member.return_value = None
        membership_id = valid_api_gateway_event['pathParameters']['membershipId']
        
        # Act
        response = handler(valid_api_gateway_event, None)
        
        # Assert
        assert response['statusCode'] == 404
        assert response['headers']['Content-Type'] == 'application/json'
        
        body = json.loads(response['body'])
        assert body['error']['code'] == 'MEMBER_NOT_FOUND'
        assert membership_id in body['error']['message']
        assert body['error']['details']['membershipId'] == membership_id
    
    def test_missing_membership_id_parameter(self, mock_db_client):
        """Test error when membership ID is missing from path parameters."""
        # Arrange
        event = {
            'httpMethod': 'GET',
            'path': '/v1/members/',
            'pathParameters': {}  # Missing membershipId
        }
        
        # Act
        response = handler(event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error']['code'] == 'INVALID_MEMBERSHIP_ID_FORMAT'
        assert 'required' in body['error']['message'].lower()
    
    def test_empty_membership_id(self, mock_db_client):
        """Test error when membership ID is empty string."""
        # Arrange
        event = {
            'httpMethod': 'GET',
            'path': '/v1/members/',
            'pathParameters': {
                'membershipId': ''
            }
        }
        
        # Act
        response = handler(event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error']['code'] == 'INVALID_MEMBERSHIP_ID_FORMAT'
    
    def test_whitespace_only_membership_id(self, mock_db_client):
        """Test error when membership ID is only whitespace."""
        # Arrange
        event = {
            'httpMethod': 'GET',
            'path': '/v1/members/',
            'pathParameters': {
                'membershipId': '   '
            }
        }
        
        # Act
        response = handler(event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error']['code'] == 'INVALID_MEMBERSHIP_ID_FORMAT'
    
    def test_null_path_parameters(self, mock_db_client):
        """Test error when pathParameters is None."""
        # Arrange
        event = {
            'httpMethod': 'GET',
            'path': '/v1/members/',
            'pathParameters': None
        }
        
        # Act
        response = handler(event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error']['code'] == 'INVALID_MEMBERSHIP_ID_FORMAT'
    
    def test_gold_tier_member_query(self, valid_api_gateway_event, mock_db_client):
        """Test query for Gold tier member."""
        # Arrange
        now = datetime.utcnow()
        gold_member = MemberProfile(
            membership_id=valid_api_gateway_event['pathParameters']['membershipId'],
            email='gold@example.com',
            name='Gold Member',
            phone='+1234567890',
            tier=Tier.GOLD,
            star_balance=800,
            annual_star_count=600,
            enrollment_date=now - timedelta(days=200),
            last_qualifying_activity=now - timedelta(days=2),
            tier_since=now - timedelta(days=50),
            next_tier_evaluation=now + timedelta(days=315)
        )
        mock_db_client.get_member.return_value = gold_member
        
        # Act
        response = handler(valid_api_gateway_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['tier'] == 'Gold'
        assert body['starBalance'] == 800
        assert body['annualStarCount'] == 600
    
    def test_reserve_tier_member_query(self, valid_api_gateway_event, mock_db_client):
        """Test query for Reserve tier member."""
        # Arrange
        now = datetime.utcnow()
        reserve_member = MemberProfile(
            membership_id=valid_api_gateway_event['pathParameters']['membershipId'],
            email='reserve@example.com',
            name='Reserve Member',
            phone='+1234567890',
            tier=Tier.RESERVE,
            star_balance=3000,
            annual_star_count=2800,
            enrollment_date=now - timedelta(days=400),
            last_qualifying_activity=now - timedelta(days=1),
            tier_since=now - timedelta(days=100),
            next_tier_evaluation=now + timedelta(days=265)
        )
        mock_db_client.get_member.return_value = reserve_member
        
        # Act
        response = handler(valid_api_gateway_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['tier'] == 'Reserve'
        assert body['starBalance'] == 3000
        assert body['annualStarCount'] == 2800
    
    def test_member_with_zero_balance(self, valid_api_gateway_event, mock_db_client):
        """Test query for member with zero star balance."""
        # Arrange
        now = datetime.utcnow()
        zero_balance_member = MemberProfile(
            membership_id=valid_api_gateway_event['pathParameters']['membershipId'],
            email='zero@example.com',
            name='Zero Balance',
            phone='+1234567890',
            tier=Tier.GREEN,
            star_balance=0,
            annual_star_count=0,
            enrollment_date=now - timedelta(days=1),
            last_qualifying_activity=None,
            tier_since=now - timedelta(days=1),
            next_tier_evaluation=now + timedelta(days=364)
        )
        mock_db_client.get_member.return_value = zero_balance_member
        
        # Act
        response = handler(valid_api_gateway_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['starBalance'] == 0
        assert body['annualStarCount'] == 0
        assert body['lastActivity'] is None
    
    def test_member_without_last_activity(self, valid_api_gateway_event, mock_db_client):
        """Test query for member with no last qualifying activity."""
        # Arrange
        now = datetime.utcnow()
        new_member = MemberProfile(
            membership_id=valid_api_gateway_event['pathParameters']['membershipId'],
            email='new@example.com',
            name='New Member',
            phone='+1234567890',
            tier=Tier.GREEN,
            star_balance=0,
            annual_star_count=0,
            enrollment_date=now,
            last_qualifying_activity=None,
            tier_since=now,
            next_tier_evaluation=now + timedelta(days=365)
        )
        mock_db_client.get_member.return_value = new_member
        
        # Act
        response = handler(valid_api_gateway_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['lastActivity'] is None
    
    def test_database_error_handling(self, valid_api_gateway_event, mock_db_client):
        """Test handling of database errors."""
        # Arrange
        mock_db_client.get_member.side_effect = Exception("Database connection failed")
        
        # Act
        response = handler(valid_api_gateway_event, None)
        
        # Assert
        assert response['statusCode'] == 500
        body = json.loads(response['body'])
        assert body['error']['code'] == 'INTERNAL_ERROR'
        assert 'unexpected error' in body['error']['message'].lower()
    
    def test_response_includes_all_required_fields(self, valid_api_gateway_event, mock_db_client, sample_member_profile):
        """Test that response includes all required fields per requirements 8.1-8.3."""
        # Arrange
        mock_db_client.get_member.return_value = sample_member_profile
        
        # Act
        response = handler(valid_api_gateway_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        
        # Verify all required fields are present (Requirements 8.1, 8.2, 8.3)
        assert 'membershipId' in body
        assert 'tier' in body  # Requirement 8.2
        assert 'starBalance' in body  # Requirement 8.1
        assert 'annualStarCount' in body  # Requirement 8.3
        assert 'enrollmentDate' in body
        assert 'tierSince' in body
        # lastActivity is optional
        assert 'lastActivity' in body
    
    def test_membership_id_trimmed(self, mock_db_client, sample_member_profile):
        """Test that membership ID with whitespace is trimmed."""
        # Arrange
        membership_id = str(uuid.uuid4())
        event = {
            'httpMethod': 'GET',
            'path': f'/v1/members/{membership_id}',
            'pathParameters': {
                'membershipId': f'  {membership_id}  '  # With whitespace
            }
        }
        sample_member_profile.membership_id = membership_id
        mock_db_client.get_member.return_value = sample_member_profile
        
        # Act
        response = handler(event, None)
        
        # Assert
        assert response['statusCode'] == 200
        # Verify trimmed ID was used
        mock_db_client.get_member.assert_called_once_with(membership_id)
    
    def test_response_format_matches_api_schema(self, valid_api_gateway_event, mock_db_client, sample_member_profile):
        """Test that response format matches the API schema from design doc."""
        # Arrange
        mock_db_client.get_member.return_value = sample_member_profile
        
        # Act
        response = handler(valid_api_gateway_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        
        # Verify field names match camelCase convention from design doc
        assert 'membershipId' in body
        assert 'starBalance' in body
        assert 'annualStarCount' in body
        assert 'enrollmentDate' in body
        assert 'lastActivity' in body
        assert 'tierSince' in body
        
        # Verify tier is string value, not enum
        assert isinstance(body['tier'], str)
        assert body['tier'] in ['Green', 'Gold', 'Reserve']
        
        # Verify dates are ISO8601 strings
        assert isinstance(body['enrollmentDate'], str)
        assert isinstance(body['tierSince'], str)
    
    def test_error_response_includes_timestamp(self, valid_api_gateway_event, mock_db_client):
        """Test that error responses include timestamp."""
        # Arrange
        mock_db_client.get_member.return_value = None
        
        # Act
        response = handler(valid_api_gateway_event, None)
        
        # Assert
        assert response['statusCode'] == 404
        body = json.loads(response['body'])
        assert 'timestamp' in body['error']
    
    def test_content_type_header_in_response(self, valid_api_gateway_event, mock_db_client, sample_member_profile):
        """Test that Content-Type header is set correctly."""
        # Arrange
        mock_db_client.get_member.return_value = sample_member_profile
        
        # Act
        response = handler(valid_api_gateway_event, None)
        
        # Assert
        assert 'headers' in response
        assert 'Content-Type' in response['headers']
        assert response['headers']['Content-Type'] == 'application/json'
    
    def test_content_type_header_in_error_response(self, valid_api_gateway_event, mock_db_client):
        """Test that Content-Type header is set in error responses."""
        # Arrange
        mock_db_client.get_member.return_value = None
        
        # Act
        response = handler(valid_api_gateway_event, None)
        
        # Assert
        assert 'headers' in response
        assert 'Content-Type' in response['headers']
        assert response['headers']['Content-Type'] == 'application/json'


class TestTransactionHistoryHandler:
    """Test cases for transaction history endpoint."""
    
    @pytest.fixture
    def transaction_history_event(self):
        """Create API Gateway event for transaction history endpoint."""
        membership_id = str(uuid.uuid4())
        return {
            'httpMethod': 'GET',
            'resource': '/v1/members/{membershipId}/transactions',
            'path': f'/v1/members/{membership_id}/transactions',
            'pathParameters': {
                'membershipId': membership_id
            },
            'queryStringParameters': None,
            'headers': {
                'Content-Type': 'application/json'
            }
        }
    
    @pytest.fixture
    def sample_transactions(self):
        """Create sample transactions for testing."""
        now = datetime.utcnow()
        return [
            Transaction(
                transaction_id=str(uuid.uuid4()),
                membership_id=str(uuid.uuid4()),
                type=TransactionType.PURCHASE,
                timestamp=now - timedelta(days=1),
                stars_earned=25,
                purchase_amount=Decimal('25.00'),
                description='Coffee purchase'
            ),
            Transaction(
                transaction_id=str(uuid.uuid4()),
                membership_id=str(uuid.uuid4()),
                type=TransactionType.REDEMPTION,
                timestamp=now - timedelta(days=2),
                stars_redeemed=60,
                description='Free drink redemption'
            ),
            Transaction(
                transaction_id=str(uuid.uuid4()),
                membership_id=str(uuid.uuid4()),
                type=TransactionType.TIER_CHANGE,
                timestamp=now - timedelta(days=30),
                description='Promoted to Gold tier'
            )
        ]
    
    def test_successful_transaction_history_query(self, transaction_history_event, mock_db_client, sample_member_profile, sample_transactions):
        """Test successful query of transaction history."""
        # Arrange
        mock_db_client.get_member.return_value = sample_member_profile
        mock_db_client.get_member_transactions.return_value = (sample_transactions, None)
        
        # Act
        response = handler(transaction_history_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        assert response['headers']['Content-Type'] == 'application/json'
        
        body = json.loads(response['body'])
        assert 'transactions' in body
        assert len(body['transactions']) == 3
        
        # Verify first transaction (purchase)
        purchase_txn = body['transactions'][0]
        assert purchase_txn['type'] == 'purchase'
        assert purchase_txn['starsEarned'] == 25
        assert purchase_txn['purchaseAmount'] == 25.0
        assert purchase_txn['description'] == 'Coffee purchase'
        assert 'timestamp' in purchase_txn
        assert 'transactionId' in purchase_txn
        
        # Verify second transaction (redemption)
        redemption_txn = body['transactions'][1]
        assert redemption_txn['type'] == 'redemption'
        assert redemption_txn['starsRedeemed'] == 60
        assert redemption_txn['description'] == 'Free drink redemption'
        
        # Verify third transaction (tier change)
        tier_txn = body['transactions'][2]
        assert tier_txn['type'] == 'tier_change'
        assert tier_txn['description'] == 'Promoted to Gold tier'
        
        # Verify no pagination token
        assert 'nextToken' not in body
        
        # Verify DynamoDB calls
        mock_db_client.get_member.assert_called_once_with(
            transaction_history_event['pathParameters']['membershipId']
        )
        mock_db_client.get_member_transactions.assert_called_once_with(
            transaction_history_event['pathParameters']['membershipId'], 50, None
        )
    
    def test_transaction_history_member_not_found(self, transaction_history_event, mock_db_client):
        """Test error when member does not exist for transaction history."""
        # Arrange
        mock_db_client.get_member.return_value = None
        membership_id = transaction_history_event['pathParameters']['membershipId']
        
        # Act
        response = handler(transaction_history_event, None)
        
        # Assert
        assert response['statusCode'] == 404
        body = json.loads(response['body'])
        assert body['error']['code'] == 'MEMBER_NOT_FOUND'
        assert membership_id in body['error']['message']
    
    def test_transaction_history_with_pagination(self, transaction_history_event, mock_db_client, sample_member_profile, sample_transactions):
        """Test transaction history with pagination parameters."""
        # Arrange
        transaction_history_event['queryStringParameters'] = {
            'limit': '10'
        }
        next_key = {'PK': 'MEMBER#123', 'SK': 'TXN#2024-01-01T00:00:00'}
        mock_db_client.get_member.return_value = sample_member_profile
        mock_db_client.get_member_transactions.return_value = (sample_transactions, next_key)
        
        # Act
        response = handler(transaction_history_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert 'transactions' in body
        assert 'nextToken' in body
        
        # Verify pagination token is base64 encoded
        import base64
        decoded_token = base64.b64decode(body['nextToken']).decode('utf-8')
        decoded_key = json.loads(decoded_token)
        assert decoded_key == next_key
        
        # Verify limit was passed correctly
        mock_db_client.get_member_transactions.assert_called_once_with(
            transaction_history_event['pathParameters']['membershipId'], 10, None
        )
    
    def test_transaction_history_with_next_token(self, transaction_history_event, mock_db_client, sample_member_profile, sample_transactions):
        """Test transaction history with next token for pagination."""
        # Arrange
        import base64
        next_key = {'PK': 'MEMBER#123', 'SK': 'TXN#2024-01-01T00:00:00'}
        encoded_token = base64.b64encode(json.dumps(next_key).encode('utf-8')).decode('utf-8')
        
        transaction_history_event['queryStringParameters'] = {
            'nextToken': encoded_token
        }
        mock_db_client.get_member.return_value = sample_member_profile
        mock_db_client.get_member_transactions.return_value = (sample_transactions, None)
        
        # Act
        response = handler(transaction_history_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        
        # Verify next token was decoded and passed correctly
        mock_db_client.get_member_transactions.assert_called_once_with(
            transaction_history_event['pathParameters']['membershipId'], 50, next_key
        )
    
    def test_transaction_history_invalid_next_token(self, transaction_history_event, mock_db_client, sample_member_profile):
        """Test error handling for invalid pagination token."""
        # Arrange
        transaction_history_event['queryStringParameters'] = {
            'nextToken': 'invalid-token'
        }
        mock_db_client.get_member.return_value = sample_member_profile
        
        # Act
        response = handler(transaction_history_event, None)
        
        # Assert
        assert response['statusCode'] == 400
        body = json.loads(response['body'])
        assert body['error']['code'] == 'INVALID_DATA_TYPE'
        assert 'Invalid pagination token' in body['error']['message']
    
    def test_transaction_history_limit_validation(self, transaction_history_event, mock_db_client, sample_member_profile, sample_transactions):
        """Test that limit is capped at 100."""
        # Arrange
        transaction_history_event['queryStringParameters'] = {
            'limit': '200'  # Above maximum
        }
        mock_db_client.get_member.return_value = sample_member_profile
        mock_db_client.get_member_transactions.return_value = (sample_transactions, None)
        
        # Act
        response = handler(transaction_history_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        
        # Verify limit was capped at 100
        mock_db_client.get_member_transactions.assert_called_once_with(
            transaction_history_event['pathParameters']['membershipId'], 100, None
        )
    
    def test_transaction_history_empty_results(self, transaction_history_event, mock_db_client, sample_member_profile):
        """Test transaction history with no transactions."""
        # Arrange
        mock_db_client.get_member.return_value = sample_member_profile
        mock_db_client.get_member_transactions.return_value = ([], None)
        
        # Act
        response = handler(transaction_history_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        assert body['transactions'] == []
        assert 'nextToken' not in body
    
    def test_transaction_history_response_format(self, transaction_history_event, mock_db_client, sample_member_profile):
        """Test transaction history response format matches API schema."""
        # Arrange
        now = datetime.utcnow()
        transactions = [
            Transaction(
                transaction_id=str(uuid.uuid4()),
                membership_id=str(uuid.uuid4()),
                type=TransactionType.PURCHASE,
                timestamp=now,
                stars_earned=15,
                purchase_amount=Decimal('12.50'),
                description='Latte purchase'
            )
        ]
        mock_db_client.get_member.return_value = sample_member_profile
        mock_db_client.get_member_transactions.return_value = (transactions, None)
        
        # Act
        response = handler(transaction_history_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        
        # Verify response structure matches design doc
        assert 'transactions' in body
        assert isinstance(body['transactions'], list)
        
        txn = body['transactions'][0]
        assert 'transactionId' in txn
        assert 'type' in txn
        assert 'timestamp' in txn
        assert 'starsEarned' in txn
        assert 'purchaseAmount' in txn
        assert 'description' in txn
        
        # Verify data types
        assert isinstance(txn['transactionId'], str)
        assert isinstance(txn['type'], str)
        assert isinstance(txn['timestamp'], str)
        assert isinstance(txn['starsEarned'], int)
        assert isinstance(txn['purchaseAmount'], float)
        assert isinstance(txn['description'], str)
    
    def test_endpoint_routing_member_profile(self, valid_api_gateway_event, mock_db_client, sample_member_profile):
        """Test that member profile endpoint is routed correctly."""
        # Arrange
        valid_api_gateway_event['resource'] = '/v1/members/{membershipId}'
        mock_db_client.get_member.return_value = sample_member_profile
        
        # Act
        response = handler(valid_api_gateway_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        
        # Should return member profile, not transactions
        assert 'membershipId' in body
        assert 'tier' in body
        assert 'starBalance' in body
        assert 'transactions' not in body
    
    def test_endpoint_routing_transaction_history(self, transaction_history_event, mock_db_client, sample_member_profile, sample_transactions):
        """Test that transaction history endpoint is routed correctly."""
        # Arrange
        mock_db_client.get_member.return_value = sample_member_profile
        mock_db_client.get_member_transactions.return_value = (sample_transactions, None)
        
        # Act
        response = handler(transaction_history_event, None)
        
        # Assert
        assert response['statusCode'] == 200
        body = json.loads(response['body'])
        
        # Should return transactions, not member profile
        assert 'transactions' in body
        assert 'membershipId' not in body
        assert 'tier' not in body
        assert 'starBalance' not in body