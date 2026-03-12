#!/bin/bash

# Manual test script - provide your own membership ID
# Usage: ./scripts/test-manual.sh [membership-id]

set -e

if [ -z "$1" ]; then
  echo "Usage: $0 <membership-id>"
  echo ""
  echo "To create a new member first, run: ./scripts/test-flow.sh"
  exit 1
fi

MEMBERSHIP_ID=$1
STACK_NAME="${STACK_NAME:-RewardsStack}"

# Get stack outputs
OUTPUTS=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query 'Stacks[0].Outputs' --output json)
EVENT_BUS_NAME=$(echo $OUTPUTS | jq -r '.[] | select(.OutputKey=="RewardsEventBusName") | .OutputValue')
API_URL=$(echo $OUTPUTS | jq -r '.[] | select(.OutputKey=="RewardsApiUrl") | .OutputValue')

echo "Event Bus: $EVENT_BUS_NAME"
echo "API URL: $API_URL"
echo "Membership ID: $MEMBERSHIP_ID"
echo ""

# Menu
echo "Select action:"
echo "1) Send purchase event"
echo "2) Send redemption event"
echo "3) Query member balance"
echo "4) Query transaction history"
echo "5) Run full flow (purchase → query)"
read -p "Choice: " choice

case $choice in
  1)
    read -p "Purchase amount: " amount
    read -p "Double star day? (y/n): " double
    read -p "Personal cup? (y/n): " cup
    
    DOUBLE_STAR=$([ "$double" == "y" ] && echo "true" || echo "false")
    PERSONAL_CUP=$([ "$cup" == "y" ] && echo "true" || echo "false")
    
    TXN_ID=$(uuidgen)
    TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    
    aws events put-events --entries "[{
      \"Source\": \"rewards.program\",
      \"DetailType\": \"rewards.transaction.purchase\",
      \"Detail\": \"{\\\"transactionId\\\":\\\"$TXN_ID\\\",\\\"timestamp\\\":\\\"$TIMESTAMP\\\",\\\"data\\\":{\\\"membershipId\\\":\\\"$MEMBERSHIP_ID\\\",\\\"amount\\\":$amount,\\\"doubleStarDay\\\":$DOUBLE_STAR,\\\"personalCup\\\":$PERSONAL_CUP}}\",
      \"EventBusName\": \"$EVENT_BUS_NAME\"
    }]"
    
    echo "✅ Purchase event sent (txn: $TXN_ID)"
    echo "⏳ Wait a few seconds, then query balance to see updated stars"
    ;;
    
  2)
    read -p "Stars to redeem: " stars
    read -p "Item description: " item
    
    TXN_ID=$(uuidgen)
    TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    
    aws events put-events --entries "[{
      \"Source\": \"rewards.program\",
      \"DetailType\": \"rewards.transaction.redemption\",
      \"Detail\": \"{\\\"transactionId\\\":\\\"$TXN_ID\\\",\\\"timestamp\\\":\\\"$TIMESTAMP\\\",\\\"data\\\":{\\\"membershipId\\\":\\\"$MEMBERSHIP_ID\\\",\\\"starsToRedeem\\\":$stars,\\\"itemDescription\\\":\\\"$item\\\"}}\",
      \"EventBusName\": \"$EVENT_BUS_NAME\"
    }]"
    
    echo "✅ Redemption event sent (txn: $TXN_ID)"
    echo "⏳ Wait a few seconds, then query balance to see updated stars"
    ;;
    
  3)
    echo "Member Balance:"
    curl -s "${API_URL}members/${MEMBERSHIP_ID}" | jq '.'
    ;;
    
  4)
    echo "Transaction History:"
    curl -s "${API_URL}members/${MEMBERSHIP_ID}/transactions" | jq '.'
    ;;
    
  5)
    echo "💳 Sending purchase for \$50.00..."
    TXN_ID=$(uuidgen)
    TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
    
    aws events put-events --entries "[{
      \"Source\": \"rewards.program\",
      \"DetailType\": \"rewards.transaction.purchase\",
      \"Detail\": \"{\\\"transactionId\\\":\\\"$TXN_ID\\\",\\\"timestamp\\\":\\\"$TIMESTAMP\\\",\\\"data\\\":{\\\"membershipId\\\":\\\"$MEMBERSHIP_ID\\\",\\\"amount\\\":50.00,\\\"doubleStarDay\\\":false,\\\"personalCup\\\":false}}\",
      \"EventBusName\": \"$EVENT_BUS_NAME\"
    }]" > /dev/null
    
    echo "✅ Purchase sent (txn: $TXN_ID)"
    echo "⏳ Waiting 5 seconds..."
    sleep 5
    
    echo ""
    echo "💰 Member Balance:"
    curl -s "${API_URL}members/${MEMBERSHIP_ID}" | jq '.'
    
    echo ""
    echo "📜 Transaction History:"
    curl -s "${API_URL}members/${MEMBERSHIP_ID}/transactions" | jq '.'
    ;;
    
  *)
    echo "Invalid choice"
    exit 1
    ;;
esac
