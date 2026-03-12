#!/usr/bin/env python3
"""Integration test script for enrollment and purchase handlers."""

import json
import uuid
import time
from datetime import datetime
import boto3
from decimal import Decimal

# Initialize AWS clients
eventbridge = boto3.client('events', region_name='us-east-1')
dynamodb = boto3.resource('dynamodb', region_name='us-east-1')

# Configuration
EVENT_BUS_NAME = 'rewards-program-events'
TABLE_NAME = 'rewards-program'

table = dynamodb.Table(TABLE_NAME)


def send_event(detail_type: str, detail: dict) -> str:
    """Send an event to EventBridge."""
    response = eventbridge.put_events(
        Entries=[
            {
                'Source': 'rewards.program',
                'DetailType': detail_type,
                'Detail': json.dumps({
                    'event_type': detail_type,
                    'transaction_id': detail.get('transactionId'),
                    'timestamp': detail.get('timestamp'),
                    'data': detail.get('data')
                }),
                'EventBusName': EVENT_BUS_NAME
            }
        ]
    )
    
    if response['FailedEntryCount'] > 0:
        raise Exception(f"Failed to send event: {response['Entries'][0]}")
    
    return detail.get('transactionId', 'unknown')


def get_member(membership_id: str) -> dict:
    """Get member profile from DynamoDB."""
    response = table.get_item(
        Key={
            'PK': f'MEMBER#{membership_id}',
            'SK': 'PROFILE'
        }
    )
    return response.get('Item')


def test_enrollment():
    """Test enrollment flow."""
    print("\n=== Testing Enrollment Flow ===")
    
    transaction_id = str(uuid.uuid4())
    event_detail = {
        'transactionId': transaction_id,
        'timestamp': datetime.utcnow().isoformat(),
        'data': {
            'email': 'test@example.com',
            'name': 'Test User',
            'phone': '+1234567890'
        }
    }
    
    print(f"Sending signup event (txn: {transaction_id})...")
    send_event('rewards.member.signup', event_detail)
    
    # Wait for Lambda to process
    print("Waiting 5 seconds for processing...")
    time.sleep(5)
    
    # Query DynamoDB for the transaction record
    print("Checking for transaction record...")
    response = table.query(
        IndexName='GSI2',
        KeyConditionExpression='GSI2PK = :txn_id',
        ExpressionAttributeValues={
            ':txn_id': f'TXN#{transaction_id}'
        }
    )
    
    if response['Items']:
        txn_record = response['Items'][0]
        membership_id = txn_record.get('membershipId')
        print(f"✓ Transaction recorded: {membership_id}")
        
        # Get member profile
        member = get_member(membership_id)
        if member:
            print(f"✓ Member profile created:")
            print(f"  - Membership ID: {member['membershipId']}")
            print(f"  - Email: {member['email']}")
            print(f"  - Tier: {member['tier']}")
            print(f"  - Star Balance: {member['starBalance']}")
            print(f"  - Annual Star Count: {member['annualStarCount']}")
            return membership_id
        else:
            print("✗ Member profile not found")
            return None
    else:
        print("✗ Transaction not recorded")
        return None


def test_purchase(membership_id: str, tier: str, amount: float, 
                  double_star_day: bool = False, personal_cup: bool = False):
    """Test purchase flow."""
    print(f"\n=== Testing Purchase Flow ({tier} tier, ${amount}) ===")
    
    # Get initial balance
    member_before = get_member(membership_id)
    initial_balance = member_before['starBalance']
    print(f"Initial balance: {initial_balance} stars")
    
    transaction_id = str(uuid.uuid4())
    event_detail = {
        'transactionId': transaction_id,
        'timestamp': datetime.utcnow().isoformat(),
        'data': {
            'membership_id': membership_id,  # Changed from membershipId
            'amount': amount,
            'double_star_day': double_star_day,  # Changed from doubleStarDay
            'personal_cup': personal_cup
        }
    }
    
    print(f"Sending purchase event (txn: {transaction_id})...")
    send_event('rewards.transaction.purchase', event_detail)
    
    # Wait for Lambda to process
    print("Waiting 5 seconds for processing...")
    time.sleep(5)
    
    # Get updated balance
    member_after = get_member(membership_id)
    new_balance = member_after['starBalance']
    stars_earned = new_balance - initial_balance
    
    # Calculate expected stars
    tier_rates = {'Green': 1.0, 'Gold': 1.2, 'Reserve': 1.7}
    expected_stars = amount * tier_rates[tier]
    if double_star_day:
        expected_stars *= 2
    if personal_cup:
        expected_stars *= 2
    
    print(f"✓ Purchase processed:")
    print(f"  - Stars earned: {stars_earned}")
    print(f"  - Expected stars: {expected_stars}")
    print(f"  - New balance: {new_balance}")
    print(f"  - Annual star count: {member_after['annualStarCount']}")
    
    # Verify calculation
    if abs(float(stars_earned) - expected_stars) < 0.01:
        print("✓ Star calculation correct")
    else:
        print(f"✗ Star calculation incorrect (expected {expected_stars}, got {stars_earned})")
    
    return stars_earned


def test_idempotency(membership_id: str):
    """Test idempotent duplicate transaction."""
    print("\n=== Testing Idempotency ===")
    
    # Get initial balance
    member_before = get_member(membership_id)
    initial_balance = member_before['starBalance']
    
    transaction_id = str(uuid.uuid4())
    event_detail = {
        'transactionId': transaction_id,
        'timestamp': datetime.utcnow().isoformat(),
        'data': {
            'membershipId': membership_id,
            'amount': 10.0,
            'doubleStarDay': False,
            'personalCup': False
        }
    }
    
    print(f"Sending first purchase event (txn: {transaction_id})...")
    send_event('rewards.transaction.purchase', event_detail)
    time.sleep(5)
    
    member_after_first = get_member(membership_id)
    balance_after_first = member_after_first['starBalance']
    stars_first = balance_after_first - initial_balance
    print(f"First purchase: earned {stars_first} stars")
    
    print(f"Sending duplicate purchase event (same txn: {transaction_id})...")
    send_event('rewards.transaction.purchase', event_detail)
    time.sleep(5)
    
    member_after_second = get_member(membership_id)
    balance_after_second = member_after_second['starBalance']
    
    if balance_after_second == balance_after_first:
        print("✓ Idempotency working: balance unchanged on duplicate")
    else:
        print(f"✗ Idempotency failed: balance changed from {balance_after_first} to {balance_after_second}")


def main():
    """Run all integration tests."""
    print("=" * 60)
    print("Rewards Program Backend - Integration Tests")
    print("=" * 60)
    
    try:
        # Test 1: Enrollment
        membership_id = test_enrollment()
        if not membership_id:
            print("\n✗ Enrollment test failed, cannot continue")
            return
        
        # Test 2: Purchase for Green tier
        test_purchase(membership_id, 'Green', 50.0)
        
        # Test 3: Purchase with double star day
        test_purchase(membership_id, 'Green', 25.0, double_star_day=True)
        
        # Test 4: Purchase with personal cup
        test_purchase(membership_id, 'Green', 15.0, personal_cup=True)
        
        # Test 5: Purchase with both multipliers
        test_purchase(membership_id, 'Green', 10.0, double_star_day=True, personal_cup=True)
        
        # Test 6: Idempotency
        test_idempotency(membership_id)
        
        print("\n" + "=" * 60)
        print("✓ All integration tests completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
