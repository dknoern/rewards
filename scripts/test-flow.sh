#!/bin/bash

# Rewards Program End-to-End Test Script
# Tests enrollment → purchase → query flow

set -e

echo "🚀 Starting Rewards Program E2E Test"
echo "======================================"

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get stack outputs
echo -e "\n${BLUE}📦 Fetching stack outputs...${NC}"
STACK_NAME="${STACK_NAME:-RewardsStack}"
OUTPUTS=$(aws cloudformation describe-stacks --stack-name $STACK_NAME --query 'Stacks[0].Outputs' --output json)

EVENT_BUS_NAME=$(echo $OUTPUTS | jq -r '.[] | select(.OutputKey=="RewardsEventBusName") | .OutputValue')
API_URL=$(echo $OUTPUTS | jq -r '.[] | select(.OutputKey=="RewardsApiUrl") | .OutputValue')

if [ -z "$EVENT_BUS_NAME" ] || [ -z "$API_URL" ]; then
  echo "❌ Error: Could not find EventBusName or ApiUrl in stack outputs"
  echo "Available outputs:"
  echo $OUTPUTS | jq '.'
  exit 1
fi

echo "Event Bus: $EVENT_BUS_NAME"
echo "API URL: $API_URL"

# Step 1: Send enrollment event
echo -e "\n${BLUE}👤 Step 1: Enrolling new member...${NC}"
ENROLLMENT_TXN_ID=$(uuidgen)
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)

aws events put-events --entries "[
  {
    \"Source\": \"rewards.program\",
    \"DetailType\": \"rewards.member.signup\",
    \"Detail\": \"{\\\"event_type\\\":\\\"rewards.member.signup\\\",\\\"transaction_id\\\":\\\"$ENROLLMENT_TXN_ID\\\",\\\"timestamp\\\":\\\"$TIMESTAMP\\\",\\\"data\\\":{\\\"email\\\":\\\"test@example.com\\\",\\\"name\\\":\\\"Test User\\\",\\\"phone\\\":\\\"+1234567890\\\"}}\",
    \"EventBusName\": \"$EVENT_BUS_NAME\"
  }
]" > /dev/null

echo "✅ Enrollment event sent (txn: $ENROLLMENT_TXN_ID)"
echo -e "${YELLOW}⏳ Waiting 5 seconds for Lambda to process...${NC}"
sleep 5

# Get membership ID from DynamoDB (more reliable than logs)
echo -e "\n${BLUE}🔍 Fetching membership ID from DynamoDB...${NC}"
TABLE_NAME="rewards-program"

# Scan for the most recent member (this is a test script, scan is acceptable)
MEMBERSHIP_ID=$(aws dynamodb scan \
  --table-name $TABLE_NAME \
  --filter-expression "begins_with(PK, :pk) AND SK = :sk" \
  --expression-attribute-values '{":pk":{"S":"MEMBER#"},":sk":{"S":"PROFILE"}}' \
  --query 'Items | sort_by(@, &enrollmentDate.S) | [-1].membershipId.S' \
  --output text)

if [ -z "$MEMBERSHIP_ID" ] || [ "$MEMBERSHIP_ID" == "None" ]; then
  echo "❌ Could not extract membership ID from DynamoDB"
  echo "Please check if the enrollment event was processed successfully"
  exit 1
fi

echo "✅ Membership ID: $MEMBERSHIP_ID"

# Step 2: Send purchase event
echo -e "\n${BLUE}💳 Step 2: Processing purchase transaction...${NC}"
PURCHASE_TXN_ID=$(uuidgen)
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
PURCHASE_AMOUNT=25.50

aws events put-events --entries "[
  {
    \"Source\": \"rewards.program\",
    \"DetailType\": \"rewards.transaction.purchase\",
    \"Detail\": \"{\\\"event_type\\\":\\\"rewards.transaction.purchase\\\",\\\"transaction_id\\\":\\\"$PURCHASE_TXN_ID\\\",\\\"timestamp\\\":\\\"$TIMESTAMP\\\",\\\"data\\\":{\\\"membership_id\\\":\\\"$MEMBERSHIP_ID\\\",\\\"amount\\\":$PURCHASE_AMOUNT,\\\"double_star_day\\\":false,\\\"personal_cup\\\":false}}\",
    \"EventBusName\": \"$EVENT_BUS_NAME\"
  }
]" > /dev/null

echo "✅ Purchase event sent (txn: $PURCHASE_TXN_ID, amount: \$$PURCHASE_AMOUNT)"
echo -e "${YELLOW}⏳ Waiting 5 seconds for Lambda to process...${NC}"
sleep 5

# Step 3: Query member balance
echo -e "\n${BLUE}💰 Step 3: Querying member balance...${NC}"
BALANCE_RESPONSE=$(curl -s "${API_URL}members/${MEMBERSHIP_ID}")

echo "Member Balance:"
echo $BALANCE_RESPONSE | jq '.'

# Step 4: Query transaction history
echo -e "\n${BLUE}📜 Step 4: Querying transaction history...${NC}"
HISTORY_RESPONSE=$(curl -s "${API_URL}members/${MEMBERSHIP_ID}/transactions")

echo "Transaction History:"
echo $HISTORY_RESPONSE | jq '.'

# Summary
echo -e "\n${GREEN}✅ Test Complete!${NC}"
echo "======================================"
echo "Membership ID: $MEMBERSHIP_ID"
echo "Expected Stars: 25.5 (Green tier: 1 star per \$1)"
echo ""
echo "To test redemption, run:"
echo "  aws events put-events --entries '[{\"Source\":\"rewards.program\",\"DetailType\":\"rewards.transaction.redemption\",\"Detail\":\"{\\\"event_type\\\":\\\"rewards.transaction.redemption\\\",\\\"transaction_id\\\":\\\"$(uuidgen)\\\",\\\"timestamp\\\":\\\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\\\",\\\"data\\\":{\\\"membership_id\\\":\\\"$MEMBERSHIP_ID\\\",\\\"stars_to_redeem\\\":60,\\\"item_description\\\":\\\"Free Coffee\\\"}}\",\"EventBusName\":\"$EVENT_BUS_NAME\"}]'"
