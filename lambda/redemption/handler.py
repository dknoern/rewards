"""Lambda handler for redemption transaction events."""

import json
from datetime import datetime
from typing import Any, Dict

from common.dynamodb import DynamoDBClient
from common.models import Transaction, TransactionType
from common.validation import (
    validate_event_message,
    validate_redemption_data,
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


@with_structured_logging('redemption')
def handler(event: Dict[str, Any], context: Any, logger: StructuredLogger) -> Dict[str, Any]:
    """
    Handle redemption transaction events.
    
    Processes redemption events by:
    - Validating membership ID exists
    - Validating star balance is sufficient (conditional update)
    - Validating minimum redemption threshold (60 stars)
    - Deducting stars atomically from balance
    - Recording redemption transaction with item description
    - Implementing idempotency using transaction ID
    
    Args:
        event: EventBridge event containing redemption data
        context: Lambda context object
        logger: Structured logger instance
        
    Returns:
        Response dictionary with status and redemption details or error
    """
    db_client = DynamoDBClient()
    
    try:
        # Extract event data from EventBridge event structure
        if 'detail' in event:
            # This is an EventBridge event
            event_data = event['detail']
            logger.info("Processing EventBridge redemption event", 
                       source=event.get('source'), 
                       detail_type=event.get('detail-type'))
        else:
            # This is a direct event (for testing)
            event_data = event
            logger.info("Processing direct redemption event")
            
        # Validate event message structure
        with create_xray_subsegment('validate_event_message'):
            event_msg = validate_event_message(event_data)
            logger.debug("Redemption event validation successful", 
                        transaction_id=event_msg.transaction_id)
        
        # Check for idempotency
        with create_xray_subsegment('check_idempotency'):
            existing_txn = db_client.check_transaction_exists(event_msg.transaction_id)
            if existing_txn:
                logger.info("Idempotent redemption request detected", 
                           transaction_id=event_msg.transaction_id,
                           existing_member_id=existing_txn.get('membershipId'))
                log_event_processing(logger, 'redemption', 
                                   existing_txn.get('membershipId'), 
                                   success=True, idempotent=True)
                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'message': 'Redemption already processed (idempotent)',
                        'membershipId': existing_txn.get('membershipId'),
                        'starsRedeemed': existing_txn.get('starsRedeemed', 0),
                        'transactionId': event_msg.transaction_id
                    })
                }
        
        # Validate redemption data (includes minimum 60 stars check)
        with create_xray_subsegment('validate_redemption_data'):
            redemption_data = validate_redemption_data(event_msg.data)
            logger.debug("Redemption data validation successful", 
                        stars_to_redeem=redemption_data.stars_to_redeem,
                        item_description=redemption_data.item_description)
        
        # Validate membership ID exists
        with create_xray_subsegment('get_member_profile'):
            start_time = datetime.utcnow()
            member = db_client.get_member(redemption_data.membership_id)
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            if not member:
                logger.warning("Redemption attempted for non-existent member", 
                              member_id=redemption_data.membership_id)
                log_dynamodb_operation(logger, 'get_item', 'rewards-program', 
                                     {'PK': f'MEMBER#{redemption_data.membership_id}'}, 
                                     success=False, error="Member not found", 
                                     duration_ms=duration_ms)
                log_event_processing(logger, 'redemption', redemption_data.membership_id, 
                                   success=False, error="MEMBER_NOT_FOUND")
                return {
                    'statusCode': 422,
                    'body': json.dumps(create_error_response(
                        ErrorCode.MEMBER_NOT_FOUND,
                        f"Member with ID {redemption_data.membership_id} does not exist",
                        {'membershipId': redemption_data.membership_id}
                    ))
                }
            
            log_dynamodb_operation(logger, 'get_item', 'rewards-program', 
                                 {'PK': f'MEMBER#{redemption_data.membership_id}'}, 
                                 success=True, duration_ms=duration_ms)
        
        # Validate sufficient star balance
        if member.star_balance < redemption_data.stars_to_redeem:
            logger.warning("Insufficient star balance for redemption", 
                          member_id=redemption_data.membership_id,
                          available_stars=member.star_balance,
                          requested_stars=redemption_data.stars_to_redeem)
            log_event_processing(logger, 'redemption', redemption_data.membership_id, 
                               success=False, error="INSUFFICIENT_STARS",
                               available_stars=member.star_balance,
                               requested_stars=redemption_data.stars_to_redeem)
            return {
                'statusCode': 422,
                'body': json.dumps(create_error_response(
                    ErrorCode.INSUFFICIENT_STARS,
                    f"Insufficient star balance. Available: {member.star_balance}, Required: {redemption_data.stars_to_redeem}",
                    {
                        'membershipId': redemption_data.membership_id,
                        'availableStars': member.star_balance,
                        'requestedStars': redemption_data.stars_to_redeem
                    }
                ))
            }
        
        # Deduct stars atomically using conditional update
        now = datetime.utcnow()
        with create_xray_subsegment('update_member_balance'):
            try:
                start_time = datetime.utcnow()
                db_client.update_member_balance(
                    membership_id=redemption_data.membership_id,
                    star_delta=-redemption_data.stars_to_redeem,
                    annual_star_delta=0  # Redemptions don't affect annual count
                )
                duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                log_dynamodb_operation(logger, 'update_item', 'rewards-program', 
                                     {'PK': f'MEMBER#{redemption_data.membership_id}'}, 
                                     success=True, duration_ms=duration_ms)
                
                logger.info("Stars deducted successfully", 
                           member_id=redemption_data.membership_id,
                           stars_redeemed=redemption_data.stars_to_redeem,
                           remaining_balance=member.star_balance - redemption_data.stars_to_redeem)
                
            except ValueError as e:
                # Conditional update failed - insufficient balance
                logger.error("Conditional update failed during redemption", 
                            member_id=redemption_data.membership_id,
                            error_message=str(e))
                log_event_processing(logger, 'redemption', redemption_data.membership_id, 
                                   success=False, error="CONDITIONAL_UPDATE_FAILED")
                return {
                    'statusCode': 422,
                    'body': json.dumps(create_error_response(
                        ErrorCode.INSUFFICIENT_STARS,
                        str(e),
                        {
                            'membershipId': redemption_data.membership_id,
                            'requestedStars': redemption_data.stars_to_redeem
                        }
                    ))
                }
        
        # Record redemption transaction
        transaction = Transaction(
            transaction_id=event_msg.transaction_id,
            membership_id=redemption_data.membership_id,
            type=TransactionType.REDEMPTION,
            timestamp=now,
            stars_redeemed=redemption_data.stars_to_redeem,
            description=redemption_data.item_description
        )
        
        with create_xray_subsegment('record_transaction'):
            start_time = datetime.utcnow()
            db_client.record_transaction(transaction)
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            log_dynamodb_operation(logger, 'put_item', 'rewards-program', 
                                 {'PK': f'MEMBER#{redemption_data.membership_id}'}, 
                                 success=True, duration_ms=duration_ms)
        
        log_event_processing(logger, 'redemption', redemption_data.membership_id, 
                           success=True, stars_redeemed=redemption_data.stars_to_redeem,
                           item_description=redemption_data.item_description,
                           transaction_id=event_msg.transaction_id)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Redemption processed successfully',
                'membershipId': redemption_data.membership_id,
                'starsRedeemed': redemption_data.stars_to_redeem,
                'itemDescription': redemption_data.item_description,
                'transactionId': event_msg.transaction_id
            })
        }
        
    except ValidationException as e:
        logger.warning("Redemption validation failed", 
                      error_code=e.code, error_message=e.message, 
                      validation_details=e.details)
        log_event_processing(logger, 'redemption', success=False, 
                           error=f"{e.code}: {e.message}")
        return {
            'statusCode': 400,
            'body': json.dumps(create_error_response(
                e.code,
                e.message,
                e.details
            ))
        }
    except ValueError as e:
        # Handle specific business logic errors
        error_msg = str(e)
        if "not found" in error_msg.lower():
            code = ErrorCode.MEMBER_NOT_FOUND
        elif "insufficient" in error_msg.lower():
            code = ErrorCode.INSUFFICIENT_STARS
        else:
            code = ErrorCode.INTERNAL_ERROR
        
        logger.error("Redemption business logic error", 
                    error_message=error_msg, error_code=code)
        log_event_processing(logger, 'redemption', success=False, 
                           error=code)
        return {
            'statusCode': 422,
            'body': json.dumps(create_error_response(
                code,
                error_msg
            ))
        }
    except Exception as e:
        logger.error("Unexpected redemption error", 
                    exception_type=type(e).__name__, 
                    exception_message=str(e))
        log_event_processing(logger, 'redemption', success=False, 
                           error="INTERNAL_ERROR")
        return {
            'statusCode': 500,
            'body': json.dumps(create_error_response(
                ErrorCode.INTERNAL_ERROR,
                'An unexpected error occurred processing the redemption'
            ))
        }
