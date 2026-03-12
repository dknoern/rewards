#!/bin/bash

# Utility functions for Rewards Program Backend
# Usage: source scripts/utils.sh

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to check stack status
check_stack_status() {
    local environment=${1:-dev}
    local stack_name="rewards-${environment}"
    
    echo -e "${BLUE}📊 Checking stack status for $environment...${NC}"
    
    if aws cloudformation describe-stacks --stack-name $stack_name &>/dev/null; then
        local status=$(aws cloudformation describe-stacks --stack-name $stack_name --query 'Stacks[0].StackStatus' --output text)
        echo -e "${GREEN}Stack Status: $status${NC}"
        
        # Show outputs
        echo -e "${BLUE}Stack Outputs:${NC}"
        aws cloudformation describe-stacks --stack-name $stack_name --query 'Stacks[0].Outputs' --output table
    else
        echo -e "${YELLOW}Stack does not exist${NC}"
    fi
}

# Function to get API endpoint
get_api_endpoint() {
    local environment=${1:-dev}
    local stack_name="rewards-${environment}"
    
    if aws cloudformation describe-stacks --stack-name $stack_name &>/dev/null; then
        local api_endpoint=$(aws cloudformation describe-stacks --stack-name $stack_name --query 'Stacks[0].Outputs[?OutputKey==`RewardsApiEndpoint`].OutputValue' --output text)
        if [ ! -z "$api_endpoint" ]; then
            echo -e "${GREEN}API Endpoint: $api_endpoint${NC}"
        else
            echo -e "${YELLOW}API endpoint not found in stack outputs${NC}"
        fi
    else
        echo -e "${RED}Stack does not exist${NC}"
    fi
}

# Function to check DLQ messages
check_dlq_messages() {
    local environment=${1:-dev}
    
    echo -e "${BLUE}🔍 Checking DLQ messages for $environment...${NC}"
    
    local queues=(
        "rewards-enrollment-dlq-${environment}"
        "rewards-purchase-dlq-${environment}"
        "rewards-redemption-dlq-${environment}"
        "rewards-tier-evaluation-dlq-${environment}"
        "rewards-expiration-dlq-${environment}"
    )
    
    for queue in "${queues[@]}"; do
        local queue_url=$(aws sqs get-queue-url --queue-name $queue --query 'QueueUrl' --output text 2>/dev/null || echo "")
        if [ ! -z "$queue_url" ]; then
            local message_count=$(aws sqs get-queue-attributes --queue-url $queue_url --attribute-names ApproximateNumberOfMessages --query 'Attributes.ApproximateNumberOfMessages' --output text)
            if [ "$message_count" -gt 0 ]; then
                echo -e "${RED}⚠️  $queue: $message_count messages${NC}"
            else
                echo -e "${GREEN}✅ $queue: No messages${NC}"
            fi
        else
            echo -e "${YELLOW}⚠️  $queue: Queue not found${NC}"
        fi
    done
}

# Function to tail Lambda logs
tail_lambda_logs() {
    local function_name=$1
    local environment=${2:-dev}
    
    if [ -z "$function_name" ]; then
        echo -e "${RED}❌ Function name required${NC}"
        echo "Usage: tail_lambda_logs <function_name> [environment]"
        echo "Available functions: enrollment, purchase, redemption, tier-evaluation, expiration, query"
        return 1
    fi
    
    local full_function_name="rewards-${function_name}-handler-${environment}"
    local log_group="/aws/lambda/${full_function_name}"
    
    echo -e "${BLUE}📋 Tailing logs for $full_function_name...${NC}"
    echo "Press Ctrl+C to stop"
    
    aws logs tail $log_group --follow
}

# Function to run smoke tests
run_smoke_tests() {
    local environment=${1:-dev}
    
    echo -e "${BLUE}🧪 Running smoke tests for $environment...${NC}"
    
    # Get API endpoint
    local stack_name="rewards-${environment}"
    local api_endpoint=$(aws cloudformation describe-stacks --stack-name $stack_name --query 'Stacks[0].Outputs[?OutputKey==`RewardsApiEndpoint`].OutputValue' --output text 2>/dev/null || echo "")
    
    if [ -z "$api_endpoint" ]; then
        echo -e "${RED}❌ Could not find API endpoint${NC}"
        return 1
    fi
    
    echo -e "${YELLOW}Testing API endpoint: $api_endpoint${NC}"
    
    # Test health check (if available)
    echo "Testing API Gateway..."
    local response=$(curl -s -o /dev/null -w "%{http_code}" "$api_endpoint/v1/health" || echo "000")
    if [ "$response" = "200" ]; then
        echo -e "${GREEN}✅ API Gateway is responding${NC}"
    else
        echo -e "${YELLOW}⚠️  API Gateway health check returned: $response${NC}"
    fi
    
    # Test invalid member query (should return 404)
    echo "Testing invalid member query..."
    local response=$(curl -s -o /dev/null -w "%{http_code}" "$api_endpoint/v1/members/00000000-0000-0000-0000-000000000000" || echo "000")
    if [ "$response" = "404" ]; then
        echo -e "${GREEN}✅ Invalid member query returns 404 as expected${NC}"
    else
        echo -e "${YELLOW}⚠️  Invalid member query returned: $response${NC}"
    fi
    
    echo -e "${GREEN}✅ Smoke tests completed${NC}"
}

# Function to show help
show_help() {
    echo -e "${BLUE}Rewards Program Backend Utilities${NC}"
    echo ""
    echo "Available functions:"
    echo "  check_stack_status [environment]     - Check CloudFormation stack status"
    echo "  get_api_endpoint [environment]       - Get API Gateway endpoint URL"
    echo "  check_dlq_messages [environment]     - Check for messages in DLQs"
    echo "  tail_lambda_logs <function> [env]    - Tail Lambda function logs"
    echo "  run_smoke_tests [environment]        - Run basic smoke tests"
    echo ""
    echo "Examples:"
    echo "  check_stack_status dev"
    echo "  tail_lambda_logs enrollment prod"
    echo "  check_dlq_messages staging"
    echo ""
    echo "Default environment: dev"
}

# If script is run directly, show help
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    show_help
fi