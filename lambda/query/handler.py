"""Lambda handler for API Gateway query requests."""

import json
from typing import Any, Dict, Optional
import base64
from datetime import datetime

from common.dynamodb import DynamoDBClient
from common.validation import (
    validate_membership_id,
    create_error_response,
    ValidationException,
    ErrorCode
)
from common.logger import (
    with_structured_logging,
    log_event_processing,
    log_dynamodb_operation,
    create_xray_subsegment,
    StructuredLogger
)


@with_structured_logging('query')
def handler(event: Dict[str, Any], context: Any, logger: StructuredLogger) -> Dict[str, Any]:
    """
    Handle API Gateway query requests for member data and transaction history.
    
    Endpoints:
    - GET /v1/members/{membershipId}
    - GET /v1/members/{membershipId}/transactions
    
    Args:
        event: API Gateway event with path parameters
        context: Lambda context object
        logger: Structured logger instance
        
    Returns:
        API Gateway response with member data or transaction history
    """
    db_client = DynamoDBClient()
    
    try:
        # Extract membership ID from path parameters
        path_params = event.get('pathParameters') or {}
        membership_id_raw = path_params.get('membershipId')
        
        # Determine endpoint based on resource path
        resource_path = event.get('resource', '')
        http_method = event.get('httpMethod', 'GET')
        
        logger.info("Processing API Gateway query request", 
                   resource_path=resource_path,
                   http_method=http_method,
                   member_id_prefix=membership_id_raw[:8] if membership_id_raw else None)
        
        # Validate membership ID format
        with create_xray_subsegment('validate_membership_id'):
            membership_id = validate_membership_id(membership_id_raw)
            logger.debug("Membership ID validation successful")
        
        if resource_path.endswith('/transactions'):
            return handle_transaction_history(db_client, membership_id, event, logger)
        else:
            return handle_member_profile(db_client, membership_id, logger)
        
    except ValidationException as e:
        logger.warning("Query validation failed", 
                      error_code=e.code, error_message=e.message, 
                      validation_details=e.details)
        log_event_processing(logger, 'query', success=False, 
                           error=f"{e.code}: {e.message}")
        return {
            'statusCode': 400,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps(create_error_response(
                e.code,
                e.message,
                e.details
            ))
        }
    except Exception as e:
        logger.error("Unexpected query error", 
                    exception_type=type(e).__name__, 
                    exception_message=str(e))
        log_event_processing(logger, 'query', success=False, 
                           error="INTERNAL_ERROR")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json'
            },
            'body': json.dumps(create_error_response(
                ErrorCode.INTERNAL_ERROR,
                'An unexpected error occurred'
            ))
        }


def handle_member_profile(db_client: DynamoDBClient, membership_id: str, logger: StructuredLogger) -> Dict[str, Any]:
    """Handle GET /v1/members/{membershipId} endpoint."""
    with create_xray_subsegment('get_member_profile'):
        start_time = datetime.utcnow()
        member = db_client.get_member(membership_id)
        duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        # Handle member not found
        if not member:
            logger.warning("Member profile not found", member_id=membership_id)
            log_dynamodb_operation(logger, 'get_item', 'rewards-program', 
                                 {'PK': f'MEMBER#{membership_id}'}, 
                                 success=False, error="Member not found", 
                                 duration_ms=duration_ms)
            log_event_processing(logger, 'member_profile_query', membership_id, 
                               success=False, error="MEMBER_NOT_FOUND")
            return {
                'statusCode': 404,
                'headers': {
                    'Content-Type': 'application/json'
                },
                'body': json.dumps(create_error_response(
                    ErrorCode.MEMBER_NOT_FOUND,
                    f"Member with ID {membership_id} does not exist",
                    {'membershipId': membership_id}
                ))
            }
        
        log_dynamodb_operation(logger, 'get_item', 'rewards-program', 
                             {'PK': f'MEMBER#{membership_id}'}, 
                             success=True, duration_ms=duration_ms)
    
    # Build response with member data
    response_data = {
        'membershipId': member.membership_id,
        'tier': member.tier.value,
        'starBalance': member.star_balance,
        'annualStarCount': member.annual_star_count,
        'enrollmentDate': member.enrollment_date.isoformat(),
        'lastActivity': member.last_qualifying_activity.isoformat() 
            if member.last_qualifying_activity else None,
        'tierSince': member.tier_since.isoformat()
    }
    
    logger.info("Member profile query successful", 
               member_id=membership_id,
               tier=member.tier.value,
               star_balance=member.star_balance,
               response_time_ms=duration_ms)
    
    log_event_processing(logger, 'member_profile_query', membership_id, 
                       success=True, tier=member.tier.value,
                       star_balance=member.star_balance)
    
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json'
        },
        'body': json.dumps(response_data)
    }


def handle_transaction_history(
    db_client: DynamoDBClient, 
    membership_id: str, 
    event: Dict[str, Any],
    logger: StructuredLogger
) -> Dict[str, Any]:
    """Handle GET /v1/members/{membershipId}/transactions endpoint."""
    # First verify member exists
    with create_xray_subsegment('verify_member_exists'):
        start_time = datetime.utcnow()
        member = db_client.get_member(membership_id)
        duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        if not member:
            logger.warning("Transaction history requested for non-existent member", 
                          member_id=membership_id)
            log_dynamodb_operation(logger, 'get_item', 'rewards-program', 
                                 {'PK': f'MEMBER#{membership_id}'}, 
                                 success=False, error="Member not found", 
                                 duration_ms=duration_ms)
            log_event_processing(logger, 'transaction_history_query', membership_id, 
                               success=False, error="MEMBER_NOT_FOUND")
            return {
                'statusCode': 404,
                'headers': {
                    'Content-Type': 'application/json'
                },
                'body': json.dumps(create_error_response(
                    ErrorCode.MEMBER_NOT_FOUND,
                    f"Member with ID {membership_id} does not exist",
                    {'membershipId': membership_id}
                ))
            }
        
        log_dynamodb_operation(logger, 'get_item', 'rewards-program', 
                             {'PK': f'MEMBER#{membership_id}'}, 
                             success=True, duration_ms=duration_ms)
    
    # Parse query parameters for pagination
    query_params = event.get('queryStringParameters') or {}
    limit = min(int(query_params.get('limit', 50)), 100)  # Max 100 per request
    next_token = query_params.get('nextToken')
    
    logger.debug("Transaction history query parameters", 
                limit=limit, has_next_token=bool(next_token))
    
    # Decode pagination token if provided
    last_evaluated_key = None
    if next_token:
        try:
            decoded_token = base64.b64decode(next_token).decode('utf-8')
            last_evaluated_key = json.loads(decoded_token)
            logger.debug("Pagination token decoded successfully")
        except Exception as e:
            logger.warning("Invalid pagination token provided", 
                          token_error=str(e))
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json'
                },
                'body': json.dumps(create_error_response(
                    ErrorCode.INVALID_DATA_TYPE,
                    'Invalid pagination token',
                    {'nextToken': next_token}
                ))
            }
    
    # Fetch transaction history
    with create_xray_subsegment('get_transaction_history'):
        start_time = datetime.utcnow()
        transactions, next_key = db_client.get_member_transactions(
            membership_id, limit, last_evaluated_key
        )
        duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        log_dynamodb_operation(logger, 'query', 'rewards-program', 
                             {'PK': f'MEMBER#{membership_id}'}, 
                             success=True, duration_ms=duration_ms)
    
    # Build transaction response data
    transaction_data = []
    for txn in transactions:
        txn_item = {
            'transactionId': txn.transaction_id,
            'type': txn.type.value,
            'timestamp': txn.timestamp.isoformat(),
        }
        
        # Add optional fields based on transaction type
        if txn.stars_earned is not None:
            txn_item['starsEarned'] = txn.stars_earned
        if txn.stars_redeemed is not None:
            txn_item['starsRedeemed'] = txn.stars_redeemed
        if txn.purchase_amount is not None:
            txn_item['purchaseAmount'] = float(txn.purchase_amount)
        if txn.description:
            txn_item['description'] = txn.description
            
        transaction_data.append(txn_item)
    
    # Build response
    response_data = {
        'transactions': transaction_data
    }
    
    # Add pagination token if there are more results
    if next_key:
        encoded_token = base64.b64encode(
            json.dumps(next_key).encode('utf-8')
        ).decode('utf-8')
        response_data['nextToken'] = encoded_token
    
    logger.info("Transaction history query successful", 
               member_id=membership_id,
               transaction_count=len(transaction_data),
               has_more_results=bool(next_key),
               response_time_ms=duration_ms)
    
    log_event_processing(logger, 'transaction_history_query', membership_id, 
                       success=True, transaction_count=len(transaction_data),
                       has_more_results=bool(next_key))
    
    return {
        'statusCode': 200,
        'headers': {
            'Content-Type': 'application/json'
        },
        'body': json.dumps(response_data)
    }
