"""DynamoDB access utilities and helper functions."""

import os
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional
import boto3
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError
from common.models import (
    MemberProfile,
    Transaction,
    StarLedgerEntry,
    Tier,
    TransactionType
)


class DynamoDBClient:
    """Client for DynamoDB operations."""
    
    def __init__(self, table_name: Optional[str] = None):
        """
        Initialize DynamoDB client.
        
        Args:
            table_name: Name of the DynamoDB table (defaults to env var)
        """
        self.dynamodb = boto3.resource('dynamodb')
        self.table_name = table_name or os.environ.get('TABLE_NAME', 'rewards-program')
        self.table = self.dynamodb.Table(self.table_name)
    
    def get_member(self, membership_id: str) -> Optional[MemberProfile]:
        """
        Retrieve a member profile by membership ID.
        
        Args:
            membership_id: Unique member identifier
            
        Returns:
            MemberProfile object if found, None otherwise
        """
        try:
            response = self.table.get_item(
                Key={
                    'PK': f'MEMBER#{membership_id}',
                    'SK': 'PROFILE'
                }
            )
            
            if 'Item' not in response:
                return None
            
            item = response['Item']
            return MemberProfile(
                membership_id=item['membershipId'],
                email=item['email'],
                name=item['name'],
                phone=item['phone'],
                tier=Tier(item['tier']),
                star_balance=int(item['starBalance']),
                annual_star_count=int(item['annualStarCount']),
                enrollment_date=datetime.fromisoformat(item['enrollmentDate']),
                last_qualifying_activity=datetime.fromisoformat(item['lastQualifyingActivity']) 
                    if item.get('lastQualifyingActivity') else None,
                tier_since=datetime.fromisoformat(item['tierSince']),
                next_tier_evaluation=datetime.fromisoformat(item['nextTierEvaluation'])
            )
        except ClientError as e:
            print(f"Error retrieving member: {e}")
            raise
    
    def create_member(self, profile: MemberProfile) -> bool:
        """
        Create a new member profile.
        
        Args:
            profile: MemberProfile object to create
            
        Returns:
            True if created successfully
            
        Raises:
            ClientError: If member already exists or other DynamoDB error
        """
        try:
            item = {
                'PK': f'MEMBER#{profile.membership_id}',
                'SK': 'PROFILE',
                'membershipId': profile.membership_id,
                'email': profile.email,
                'name': profile.name,
                'phone': profile.phone,
                'tier': profile.tier.value,
                'starBalance': profile.star_balance,
                'annualStarCount': profile.annual_star_count,
                'enrollmentDate': profile.enrollment_date.isoformat(),
                'tierSince': profile.tier_since.isoformat(),
                'nextTierEvaluation': profile.next_tier_evaluation.isoformat(),
                'GSI1PK': f'TIER#{profile.tier.value}',
                'GSI1SK': f'EVAL#{profile.next_tier_evaluation.isoformat()}'
            }
            
            if profile.last_qualifying_activity:
                item['lastQualifyingActivity'] = profile.last_qualifying_activity.isoformat()
            
            self.table.put_item(
                Item=item,
                ConditionExpression='attribute_not_exists(PK)'
            )
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                raise ValueError(f"Member {profile.membership_id} already exists")
            raise
    
    def update_member_balance(
        self,
        membership_id: str,
        star_delta: int,
        annual_star_delta: int = 0,
        last_activity: Optional[datetime] = None
    ) -> bool:
        """
        Update member's star balance atomically.
        
        Args:
            membership_id: Member to update
            star_delta: Change in star balance (positive or negative)
            annual_star_delta: Change in annual star count
            last_activity: New last qualifying activity timestamp
            
        Returns:
            True if updated successfully
            
        Raises:
            ClientError: If update fails
        """
        try:
            update_expr = 'SET starBalance = starBalance + :star_delta, annualStarCount = annualStarCount + :annual_delta'
            expr_values = {
                ':star_delta': star_delta,
                ':annual_delta': annual_star_delta
            }
            
            if last_activity:
                update_expr += ', lastQualifyingActivity = :last_activity'
                expr_values[':last_activity'] = last_activity.isoformat()
            
            # Ensure balance doesn't go negative
            # Check if current balance + delta >= 0
            condition_expr = None
            if star_delta < 0:
                condition_expr = 'starBalance >= :min_balance'
                expr_values[':min_balance'] = abs(star_delta)
            
            update_params = {
                'Key': {
                    'PK': f'MEMBER#{membership_id}',
                    'SK': 'PROFILE'
                },
                'UpdateExpression': update_expr,
                'ExpressionAttributeValues': expr_values
            }
            
            if condition_expr:
                update_params['ConditionExpression'] = condition_expr
            
            self.table.update_item(**update_params)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
                raise ValueError("Insufficient star balance")
            raise
    
    def record_transaction(self, transaction: Transaction) -> bool:
        """
        Record a transaction in the history.
        
        Args:
            transaction: Transaction object to record
            
        Returns:
            True if recorded successfully
        """
        try:
            item = {
                'PK': f'MEMBER#{transaction.membership_id}',
                'SK': f'TXN#{transaction.timestamp.isoformat()}#{transaction.transaction_id}',
                'transactionId': transaction.transaction_id,
                'membershipId': transaction.membership_id,  # Add membership_id field
                'type': transaction.type.value,
                'timestamp': transaction.timestamp.isoformat(),
                'GSI2PK': f'TXN#{transaction.transaction_id}',
                'GSI2SK': transaction.timestamp.isoformat(),
                'ttl': int((transaction.timestamp.timestamp() + 30 * 24 * 60 * 60))  # 30 days
            }
            
            if transaction.stars_earned is not None:
                item['starsEarned'] = transaction.stars_earned
            if transaction.stars_redeemed is not None:
                item['starsRedeemed'] = transaction.stars_redeemed
            if transaction.purchase_amount is not None:
                item['purchaseAmount'] = Decimal(str(transaction.purchase_amount))
            if transaction.description:
                item['description'] = transaction.description
            
            self.table.put_item(Item=item)
            return True
        except ClientError as e:
            print(f"Error recording transaction: {e}")
            raise
    
    def check_transaction_exists(self, transaction_id: str) -> Optional[Dict[str, Any]]:
        """
        Check if a transaction ID has been processed (idempotency check).
        
        Args:
            transaction_id: Transaction ID to check
            
        Returns:
            Transaction result if found (includes membershipId extracted from PK), None otherwise
        """
        try:
            response = self.table.query(
                IndexName='GSI2',
                KeyConditionExpression=Key('GSI2PK').eq(f'TXN#{transaction_id}'),
                Limit=1
            )
            
            if response['Items']:
                item = response['Items'][0]
                # Extract membership ID from PK for convenience
                if 'PK' in item and item['PK'].startswith('MEMBER#'):
                    item['membershipId'] = item['PK'].replace('MEMBER#', '')
                return item
            return None
        except ClientError as e:
            print(f"Error checking transaction: {e}")
            raise
    
    def get_member_transactions(
        self,
        membership_id: str,
        limit: int = 50,
        last_evaluated_key: Optional[Dict[str, Any]] = None
    ) -> tuple[List[Transaction], Optional[Dict[str, Any]]]:
        """
        Retrieve transaction history for a member.
        
        Args:
            membership_id: Member to query
            limit: Maximum number of transactions to return
            last_evaluated_key: Pagination token
            
        Returns:
            Tuple of (list of transactions, next pagination token)
        """
        try:
            query_params = {
                'KeyConditionExpression': Key('PK').eq(f'MEMBER#{membership_id}') & Key('SK').begins_with('TXN#'),
                'Limit': limit,
                'ScanIndexForward': False  # Most recent first
            }
            
            if last_evaluated_key:
                query_params['ExclusiveStartKey'] = last_evaluated_key
            
            response = self.table.query(**query_params)
            
            transactions = []
            for item in response['Items']:
                transactions.append(Transaction(
                    transaction_id=item['transactionId'],
                    membership_id=membership_id,
                    type=TransactionType(item['type']),
                    timestamp=datetime.fromisoformat(item['timestamp']),
                    stars_earned=item.get('starsEarned'),
                    stars_redeemed=item.get('starsRedeemed'),
                    purchase_amount=item.get('purchaseAmount'),
                    description=item.get('description')
                ))
            
            next_key = response.get('LastEvaluatedKey')
            return transactions, next_key
        except ClientError as e:
            print(f"Error retrieving transactions: {e}")
            raise
    
    def create_star_ledger_entry(self, entry: StarLedgerEntry) -> bool:
        """
        Create a star ledger entry for Green tier members.
        
        Args:
            entry: StarLedgerEntry object to create
            
        Returns:
            True if created successfully
        """
        try:
            item = {
                'PK': f'MEMBER#{entry.membership_id}',
                'SK': f'STAR#{entry.earned_date.isoformat()}#{entry.batch_id}',
                'earnedDate': entry.earned_date.isoformat(),
                'starCount': entry.star_count,
                'batchId': entry.batch_id
            }
            
            if entry.expiration_date:
                item['expirationDate'] = entry.expiration_date.isoformat()
            
            self.table.put_item(Item=item)
            return True
        except ClientError as e:
            print(f"Error creating star ledger entry: {e}")
            raise
    
    def get_star_ledger_entries(self, membership_id: str) -> List[StarLedgerEntry]:
        """
        Retrieve all star ledger entries for a member.
        
        Args:
            membership_id: Member to query
            
        Returns:
            List of StarLedgerEntry objects
        """
        try:
            response = self.table.query(
                KeyConditionExpression=Key('PK').eq(f'MEMBER#{membership_id}') & Key('SK').begins_with('STAR#')
            )
            
            entries = []
            for item in response['Items']:
                entries.append(StarLedgerEntry(
                    membership_id=membership_id,
                    earned_date=datetime.fromisoformat(item['earnedDate']),
                    star_count=int(item['starCount']),
                    expiration_date=datetime.fromisoformat(item['expirationDate']) 
                        if item.get('expirationDate') else None,
                    batch_id=item['batchId']
                ))
            
            return entries
        except ClientError as e:
            print(f"Error retrieving star ledger: {e}")
            raise
    
    def query_members_by_tier(
        self,
        tier: Tier,
        evaluation_date_before: Optional[datetime] = None,
        limit: int = 100
    ) -> List[MemberProfile]:
        """
        Query members by tier using GSI1 for tier evaluation.
        
        Args:
            tier: Tier to query (Green, Gold, or Reserve)
            evaluation_date_before: Optional filter for members with evaluation date before this
            limit: Maximum number of members to return
            
        Returns:
            List of MemberProfile objects
        """
        try:
            query_params = {
                'IndexName': 'GSI1',
                'KeyConditionExpression': Key('GSI1PK').eq(f'TIER#{tier.value}'),
                'Limit': limit
            }
            
            if evaluation_date_before:
                query_params['KeyConditionExpression'] &= Key('GSI1SK').lt(
                    f'EVAL#{evaluation_date_before.isoformat()}'
                )
            
            response = self.table.query(**query_params)
            
            members = []
            for item in response['Items']:
                members.append(MemberProfile(
                    membership_id=item['membershipId'],
                    email=item['email'],
                    name=item['name'],
                    phone=item['phone'],
                    tier=Tier(item['tier']),
                    star_balance=int(item['starBalance']),
                    annual_star_count=int(item['annualStarCount']),
                    enrollment_date=datetime.fromisoformat(item['enrollmentDate']),
                    last_qualifying_activity=datetime.fromisoformat(item['lastQualifyingActivity'])
                        if item.get('lastQualifyingActivity') else None,
                    tier_since=datetime.fromisoformat(item['tierSince']),
                    next_tier_evaluation=datetime.fromisoformat(item['nextTierEvaluation'])
                ))
            
            return members
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ResourceNotFoundException':
                raise ValueError(f"GSI1 index not found on table {self.table_name}")
            print(f"Error querying members by tier: {e}")
            raise
    
    def update_member_tier(
        self,
        membership_id: str,
        new_tier: Tier,
        tier_since: datetime,
        next_evaluation: datetime
    ) -> bool:
        """
        Update member's tier status.
        
        Args:
            membership_id: Member to update
            new_tier: New tier level
            tier_since: Timestamp of tier change
            next_evaluation: Next tier evaluation date
            
        Returns:
            True if updated successfully
            
        Raises:
            ClientError: If update fails
        """
        try:
            self.table.update_item(
                Key={
                    'PK': f'MEMBER#{membership_id}',
                    'SK': 'PROFILE'
                },
                UpdateExpression='SET tier = :tier, tierSince = :tier_since, '
                                'nextTierEvaluation = :next_eval, '
                                'GSI1PK = :gsi1pk, GSI1SK = :gsi1sk',
                ExpressionAttributeValues={
                    ':tier': new_tier.value,
                    ':tier_since': tier_since.isoformat(),
                    ':next_eval': next_evaluation.isoformat(),
                    ':gsi1pk': f'TIER#{new_tier.value}',
                    ':gsi1sk': f'EVAL#{next_evaluation.isoformat()}'
                }
            )
            return True
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ConditionalCheckFailedException':
                raise ValueError(f"Member {membership_id} not found or condition failed")
            print(f"Error updating member tier: {e}")
            raise
    
    def delete_star_ledger_entries(
        self,
        membership_id: str,
        batch_ids: List[str]
    ) -> bool:
        """
        Delete expired star ledger entries.
        
        Args:
            membership_id: Member whose entries to delete
            batch_ids: List of batch IDs to delete
            
        Returns:
            True if deleted successfully
        """
        try:
            # DynamoDB batch write supports up to 25 items
            for i in range(0, len(batch_ids), 25):
                batch = batch_ids[i:i+25]
                with self.table.batch_writer() as writer:
                    for batch_id in batch:
                        # Need to find the exact SK for each batch_id
                        # Query first to get the full key
                        response = self.table.query(
                            KeyConditionExpression=Key('PK').eq(f'MEMBER#{membership_id}') & 
                                                  Key('SK').begins_with('STAR#'),
                            FilterExpression=Attr('batchId').eq(batch_id)
                        )
                        for item in response['Items']:
                            writer.delete_item(
                                Key={
                                    'PK': item['PK'],
                                    'SK': item['SK']
                                }
                            )
            return True
        except ClientError as e:
            print(f"Error deleting star ledger entries: {e}")
            raise
    
    def update_member(self, membership_id: str, updates: Dict[str, Any]) -> bool:
        """
        Generic update method for member profile fields.
        
        Args:
            membership_id: Member to update
            updates: Dictionary of field names to new values
            
        Returns:
            True if updated successfully
            
        Raises:
            ValueError: If no updates provided or member not found
            ClientError: If update fails
        """
        if not updates:
            raise ValueError("No updates provided")
        
        try:
            # Build update expression dynamically
            update_parts = []
            expr_values = {}
            
            for key, value in updates.items():
                update_parts.append(f'{key} = :{key}')
                if isinstance(value, datetime):
                    expr_values[f':{key}'] = value.isoformat()
                elif isinstance(value, Tier):
                    expr_values[f':{key}'] = value.value
                else:
                    expr_values[f':{key}'] = value
            
            update_expr = 'SET ' + ', '.join(update_parts)
            
            self.table.update_item(
                Key={
                    'PK': f'MEMBER#{membership_id}',
                    'SK': 'PROFILE'
                },
                UpdateExpression=update_expr,
                ExpressionAttributeValues=expr_values,
                ConditionExpression='attribute_exists(PK)'
            )
            return True
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'ConditionalCheckFailedException':
                raise ValueError(f"Member {membership_id} not found")
            print(f"Error updating member: {e}")
            raise
