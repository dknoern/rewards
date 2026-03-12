#!/usr/bin/env python3
"""
Comprehensive validation script for tier evaluation and expiration handlers.

This script validates Task 10: Checkpoint - Validate tier evaluation and expiration handlers
by testing:
1. Tier evaluation logic with sample members at thresholds
2. Expiration logic with inactive Green members
3. Scheduled rules trigger correctly
4. Business logic works as expected
"""

import json
import uuid
import time
import boto3
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Optional

# AWS clients
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')
lambda_client = boto3.client('lambda', region_name='us-east-1')
eventbridge = boto3.client('events', region_name='us-east-1')

# Configuration
TABLE_NAME = 'rewards-program'
EVENT_BUS_NAME = 'rewards-program-events'

table = dynamodb.Table(TABLE_NAME)


class ValidationError(Exception):
    """Custom exception for validation failures."""
    pass


def create_test_member(membership_id: str, tier: str, star_balance: int, 
                      annual_star_count: int, enrollment_days_ago: int = 365,
                      last_activity_days_ago: Optional[int] = None) -> Dict:
    """Create a test member in DynamoDB."""
    current_time = datetime.utcnow()
    enrollment_date = current_time - timedelta(days=enrollment_days_ago)
    tier_since = enrollment_date
    next_evaluation = current_time - timedelta(days=1)  # Due for evaluation
    
    last_qualifying_activity = None
    if last_activity_days_ago is not None:
        last_qualifying_activity = current_time - timedelta(days=last_activity_days_ago)
    
    member_item = {
        'PK': f'MEMBER#{membership_id}',
        'SK': 'PROFILE',
        'membershipId': membership_id,
        'email': f'test-{membership_id}@example.com',
        'name': f'Test User {membership_id}',
        'phone': '+1234567890',
        'tier': tier,
        'starBalance': star_balance,
        'annualStarCount': annual_star_count,
        'enrollmentDate': enrollment_date.isoformat(),
        'tierSince': tier_since.isoformat(),
        'nextTierEvaluation': next_evaluation.isoformat(),
        'GSI1PK': f'TIER#{tier}',
        'GSI1SK': f'EVAL#{next_evaluation.isoformat()}'
    }
    
    if last_qualifying_activity:
        member_item['lastQualifyingActivity'] = last_qualifying_activity.isoformat()
    
    table.put_item(Item=member_item)
    print(f"✓ Created test member {membership_id} ({tier} tier, {star_balance} stars, {annual_star_count} annual)")
    return member_item


def create_purchase_transactions(membership_id: str, transactions: List[Dict]) -> None:
    """Create purchase transaction history for a member."""
    current_time = datetime.utcnow()
    
    for i, txn in enumerate(transactions):
        days_ago = txn.get('days_ago', 30)
        stars_earned = txn.get('stars_earned', 50)
        amount = txn.get('amount', 50.0)
        
        txn_time = current_time - timedelta(days=days_ago)
        txn_id = str(uuid.uuid4())
        
        # Create transaction record
        table.put_item(Item={
            'PK': f'MEMBER#{membership_id}',
            'SK': f'TXN#{txn_time.isoformat()}#{txn_id}',
            'transactionId': txn_id,
            'type': 'purchase',
            'timestamp': txn_time.isoformat(),
            'starsEarned': stars_earned,
            'purchaseAmount': Decimal(str(amount)),
            'description': f'Purchase transaction ${amount}',
            'GSI2PK': f'TXN#{txn_id}',
            'GSI2SK': txn_time.isoformat()
        })
        
        print(f"  - Added purchase transaction: {stars_earned} stars, {days_ago} days ago")


def create_star_ledger_entries(membership_id: str, entries: List[Dict]) -> None:
    """Create star ledger entries for Green tier members."""
    current_time = datetime.utcnow()
    
    for entry in entries:
        days_ago = entry.get('days_ago', 30)
        star_count = entry.get('star_count', 25)
        
        earned_date = current_time - timedelta(days=days_ago)
        batch_id = str(uuid.uuid4())
        expiration_date = earned_date + timedelta(days=180)  # 6 months
        
        table.put_item(Item={
            'PK': f'MEMBER#{membership_id}',
            'SK': f'STAR#{earned_date.isoformat()}#{batch_id}',
            'earnedDate': earned_date.isoformat(),
            'starCount': star_count,
            'expirationDate': expiration_date.isoformat(),
            'batchId': batch_id
        })
        
        print(f"  - Added star ledger entry: {star_count} stars, {days_ago} days ago")


def get_member(membership_id: str) -> Optional[Dict]:
    """Get member profile from DynamoDB."""
    try:
        response = table.get_item(
            Key={
                'PK': f'MEMBER#{membership_id}',
                'SK': 'PROFILE'
            }
        )
        return response.get('Item')
    except Exception as e:
        print(f"Error getting member {membership_id}: {e}")
        return None


def invoke_tier_evaluation_handler() -> Dict:
    """Manually invoke the tier evaluation handler."""
    print("\n=== Invoking Tier Evaluation Handler ===")
    
    try:
        response = lambda_client.invoke(
            FunctionName='rewards-tier-evaluation-handler',
            InvocationType='RequestResponse',
            Payload=json.dumps({})
        )
        
        payload = json.loads(response['Payload'].read())
        print(f"✓ Tier evaluation handler invoked successfully")
        print(f"Response: {json.dumps(payload, indent=2)}")
        return payload
        
    except Exception as e:
        print(f"✗ Error invoking tier evaluation handler: {e}")
        raise ValidationError(f"Tier evaluation handler invocation failed: {e}")


def invoke_expiration_handler() -> Dict:
    """Manually invoke the expiration handler."""
    print("\n=== Invoking Expiration Handler ===")
    
    try:
        response = lambda_client.invoke(
            FunctionName='rewards-expiration-handler',
            InvocationType='RequestResponse',
            Payload=json.dumps({})
        )
        
        payload = json.loads(response['Payload'].read())
        print(f"✓ Expiration handler invoked successfully")
        print(f"Response: {json.dumps(payload, indent=2)}")
        return payload
        
    except Exception as e:
        print(f"✗ Error invoking expiration handler: {e}")
        raise ValidationError(f"Expiration handler invocation failed: {e}")


def validate_tier_promotion(membership_id: str, expected_tier: str) -> bool:
    """Validate that a member was promoted to the expected tier."""
    member = get_member(membership_id)
    if not member:
        raise ValidationError(f"Member {membership_id} not found after tier evaluation")
    
    actual_tier = member.get('tier')
    if actual_tier == expected_tier:
        print(f"✓ Member {membership_id} correctly promoted to {expected_tier}")
        return True
    else:
        print(f"✗ Member {membership_id} tier mismatch: expected {expected_tier}, got {actual_tier}")
        return False


def validate_star_expiration(membership_id: str, expected_balance: int) -> bool:
    """Validate that stars were expired correctly."""
    member = get_member(membership_id)
    if not member:
        raise ValidationError(f"Member {membership_id} not found after expiration")
    
    actual_balance = member.get('starBalance', 0)
    if actual_balance == expected_balance:
        print(f"✓ Member {membership_id} balance correctly updated to {expected_balance}")
        return True
    else:
        print(f"✗ Member {membership_id} balance mismatch: expected {expected_balance}, got {actual_balance}")
        return False


def check_scheduled_rules() -> bool:
    """Check that scheduled EventBridge rules are configured correctly."""
    print("\n=== Checking Scheduled Rules ===")
    
    try:
        # Check tier evaluation rule
        tier_rule = eventbridge.describe_rule(Name='rewards-tier-evaluation-schedule')
        print(f"✓ Tier evaluation rule found: {tier_rule['ScheduleExpression']}")
        
        # Check expiration rule
        expiration_rule = eventbridge.describe_rule(Name='rewards-expiration-schedule')
        print(f"✓ Expiration rule found: {expiration_rule['ScheduleExpression']}")
        
        return True
        
    except Exception as e:
        print(f"✗ Error checking scheduled rules: {e}")
        return False


def test_tier_evaluation_scenarios():
    """Test tier evaluation with various member scenarios."""
    print("\n" + "="*60)
    print("TESTING TIER EVALUATION SCENARIOS")
    print("="*60)
    
    # Scenario 1: Green member with 600 annual stars (should promote to Gold)
    member_1 = str(uuid.uuid4())
    create_test_member(member_1, 'Green', 150, 600)
    create_purchase_transactions(member_1, [
        {'days_ago': 30, 'stars_earned': 100, 'amount': 100.0},
        {'days_ago': 60, 'stars_earned': 200, 'amount': 200.0},
        {'days_ago': 90, 'stars_earned': 300, 'amount': 300.0}
    ])
    
    # Scenario 2: Gold member with 2600 annual stars (should promote to Reserve)
    member_2 = str(uuid.uuid4())
    create_test_member(member_2, 'Gold', 500, 2600)
    create_purchase_transactions(member_2, [
        {'days_ago': 30, 'stars_earned': 800, 'amount': 666.0},
        {'days_ago': 60, 'stars_earned': 900, 'amount': 750.0},
        {'days_ago': 90, 'stars_earned': 900, 'amount': 750.0}
    ])
    
    # Scenario 3: Gold member with 400 annual stars (should demote to Green)
    member_3 = str(uuid.uuid4())
    create_test_member(member_3, 'Gold', 200, 400)
    create_purchase_transactions(member_3, [
        {'days_ago': 30, 'stars_earned': 100, 'amount': 83.0},
        {'days_ago': 60, 'stars_earned': 150, 'amount': 125.0},
        {'days_ago': 90, 'stars_earned': 150, 'amount': 125.0}
    ])
    
    # Scenario 4: Green member with 450 annual stars (should stay Green)
    member_4 = str(uuid.uuid4())
    create_test_member(member_4, 'Green', 100, 450)
    create_purchase_transactions(member_4, [
        {'days_ago': 30, 'stars_earned': 150, 'amount': 150.0},
        {'days_ago': 60, 'stars_earned': 150, 'amount': 150.0},
        {'days_ago': 90, 'stars_earned': 150, 'amount': 150.0}
    ])
    
    # Run tier evaluation
    tier_result = invoke_tier_evaluation_handler()
    
    # Validate results
    print("\n--- Validating Tier Evaluation Results ---")
    results = []
    results.append(validate_tier_promotion(member_1, 'Gold'))
    results.append(validate_tier_promotion(member_2, 'Reserve'))
    results.append(validate_tier_promotion(member_3, 'Green'))
    results.append(validate_tier_promotion(member_4, 'Green'))
    
    return all(results), [member_1, member_2, member_3, member_4]


def test_expiration_scenarios():
    """Test star expiration with various member scenarios."""
    print("\n" + "="*60)
    print("TESTING STAR EXPIRATION SCENARIOS")
    print("="*60)
    
    # Scenario 1: Inactive Green member with expired stars
    member_1 = str(uuid.uuid4())
    create_test_member(member_1, 'Green', 200, 100, last_activity_days_ago=60)  # 2 months ago
    create_star_ledger_entries(member_1, [
        {'days_ago': 200, 'star_count': 50},  # Expired (over 6 months)
        {'days_ago': 190, 'star_count': 75},  # Expired (over 6 months)
        {'days_ago': 100, 'star_count': 75}   # Not expired (under 6 months)
    ])
    
    # Scenario 2: Active Green member (should not expire)
    member_2 = str(uuid.uuid4())
    create_test_member(member_2, 'Green', 150, 80, last_activity_days_ago=15)  # 15 days ago
    create_star_ledger_entries(member_2, [
        {'days_ago': 200, 'star_count': 50},  # Would expire but member is active
        {'days_ago': 100, 'star_count': 100}  # Not expired
    ])
    
    # Scenario 3: Gold member (stars never expire)
    member_3 = str(uuid.uuid4())
    create_test_member(member_3, 'Gold', 300, 600, last_activity_days_ago=90)  # 3 months ago
    # Gold members don't have star ledger entries since stars don't expire
    
    # Run expiration handler
    expiration_result = invoke_expiration_handler()
    
    # Validate results
    print("\n--- Validating Expiration Results ---")
    results = []
    results.append(validate_star_expiration(member_1, 75))   # 200 - 125 expired stars
    results.append(validate_star_expiration(member_2, 150))  # No change (active member)
    results.append(validate_star_expiration(member_3, 300))  # No change (Gold member)
    
    return all(results), [member_1, member_2, member_3]


def cleanup_test_data(member_ids: List[str]):
    """Clean up test data from DynamoDB."""
    print("\n--- Cleaning Up Test Data ---")
    
    for member_id in member_ids:
        try:
            # Delete member profile
            table.delete_item(
                Key={
                    'PK': f'MEMBER#{member_id}',
                    'SK': 'PROFILE'
                }
            )
            
            # Query and delete all related records
            response = table.query(
                KeyConditionExpression='PK = :pk',
                ExpressionAttributeValues={':pk': f'MEMBER#{member_id}'}
            )
            
            for item in response.get('Items', []):
                if item['SK'] != 'PROFILE':  # Already deleted above
                    table.delete_item(
                        Key={
                            'PK': item['PK'],
                            'SK': item['SK']
                        }
                    )
            
            print(f"✓ Cleaned up data for member {member_id}")
            
        except Exception as e:
            print(f"✗ Error cleaning up member {member_id}: {e}")


def main():
    """Run comprehensive validation tests."""
    print("="*80)
    print("REWARDS PROGRAM BACKEND - TIER EVALUATION & EXPIRATION VALIDATION")
    print("="*80)
    
    all_member_ids = []
    
    try:
        # Check scheduled rules
        rules_ok = check_scheduled_rules()
        if not rules_ok:
            raise ValidationError("Scheduled rules validation failed")
        
        # Test tier evaluation
        tier_ok, tier_members = test_tier_evaluation_scenarios()
        all_member_ids.extend(tier_members)
        
        if not tier_ok:
            raise ValidationError("Tier evaluation validation failed")
        
        # Test expiration
        expiration_ok, expiration_members = test_expiration_scenarios()
        all_member_ids.extend(expiration_members)
        
        if not expiration_ok:
            raise ValidationError("Star expiration validation failed")
        
        print("\n" + "="*80)
        print("✅ ALL VALIDATION TESTS PASSED SUCCESSFULLY!")
        print("="*80)
        print("\nSummary:")
        print("✓ Scheduled EventBridge rules are configured correctly")
        print("✓ Tier evaluation handler processes members correctly")
        print("✓ Star expiration handler processes Green members correctly")
        print("✓ Business logic works as expected")
        print("\nTask 10 validation completed successfully!")
        
    except ValidationError as e:
        print(f"\n❌ VALIDATION FAILED: {e}")
        return False
        
    except Exception as e:
        print(f"\n💥 UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Clean up test data
        if all_member_ids:
            cleanup_test_data(all_member_ids)
    
    return True


if __name__ == '__main__':
    success = main()
    exit(0 if success else 1)