"""Lambda handler for purchase transaction events."""

import json
import uuid
from datetime import datetime
from typing import Any, Dict

from common.dynamodb import DynamoDBClient
from common.models import Transaction, TransactionType, Tier
from common.star_calculator import calculate_stars
from common.validation import (
    validate_event_message,
    validate_purchase_data,
    create_error_response,
    ValidationException,
    ErrorCode
)
from common.logger import (
    with_structured_logging,
    log_event_processing,
    log_dynamodb_operation,
    create_xray_subsegment,
    StructuredLogger,
    LogSampler
)


@with_structured_logging('purchase')
def handler(event: Dict[str, Any], context: Any, logger: StructuredLogger) -> Dict[str, Any]:
    """
    Handle purchase transaction events.
    
    Processes purchase events by:
    - Validating membership ID exists
    - Calculating stars using tier rate and multipliers
    - Updating star balance atomically
    - Updating last qualifying activity timestamp
    - Updating annual star count
    - Creating star ledger entry for Green members
    - Recording purchase transaction
    - Implementing idempotency using transaction ID
    
    Args:
        event: EventBridge event containing purchase data
        context: Lambda context object
        logger: Structured logger instance
        
    Returns:
        Response dictionary with status and stars earned or error
    """
    db_client = DynamoDBClient()
    # Use log sampling for high-volume purchase operations
    sampler = LogSampler(sample_rate=0.1)  # Log 10% of purchase operations
    
    try:
        # Extract event data from EventBridge event structure
        if 'detail' in event:
            # This is an EventBridge event
            event_data = event['detail']
            if sampler.should_log():
                logger.info("Processing EventBridge purchase event", 
                           source=event.get('source'), 
                           detail_type=event.get('detail-type'))
        else:
            # This is a direct event (for testing)
            event_data = event
            logger.info("Processing direct purchase event")
            
        # Validate event message structure
        with create_xray_subsegment('validate_event_message'):
            event_msg = validate_event_message(event_data)
            if sampler.should_log():
                logger.debug("Purchase event validation successful", 
                            transaction_id=event_msg.transaction_id)
        
        # Check for idempotency
        with create_xray_subsegment('check_idempotency'):
            existing_txn = db_client.check_transaction_exists(event_msg.transaction_id)
            if existing_txn:
                logger.info("Idempotent purchase request detected", 
                           transaction_id=event_msg.transaction_id,
                           existing_member_id=existing_txn.get('membershipId'))
                log_event_processing(logger, 'purchase', 
                                   existing_txn.get('membershipId'), 
                                   success=True, idempotent=True)
                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'message': 'Purchase already processed (idempotent)',
                        'membershipId': existing_txn.get('membershipId'),
                        'starsEarned': existing_txn.get('starsEarned', 0),
                        'transactionId': event_msg.transaction_id
                    })
                }
        
        # Validate purchase data
        with create_xray_subsegment('validate_purchase_data'):
            purchase_data = validate_purchase_data(event_msg.data)
            if sampler.should_log():
                logger.debug("Purchase data validation successful", 
                            amount=float(purchase_data.amount),
                            double_star_day=purchase_data.double_star_day,
                            personal_cup=purchase_data.personal_cup)
        
        # Validate membership ID exists
        with create_xray_subsegment('get_member_profile'):
            start_time = datetime.utcnow()
            member = db_client.get_member(purchase_data.membership_id)
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            if not member:
                logger.warning("Purchase attempted for non-existent member", 
                              member_id=purchase_data.membership_id)
                log_event_processing(logger, 'purchase', purchase_data.membership_id, 
                                   success=False, error="MEMBER_NOT_FOUND")
                return {
                    'statusCode': 422,
                    'body': json.dumps(create_error_response(
                        ErrorCode.MEMBER_NOT_FOUND,
                        f"Member with ID {purchase_data.membership_id} does not exist",
                        {'membershipId': purchase_data.membership_id}
                    ))
                }
            
            log_dynamodb_operation(logger, 'get_item', 'rewards-program', 
                                 {'PK': f'MEMBER#{purchase_data.membership_id}'}, 
                                 success=True, duration_ms=duration_ms)
        
        # Calculate stars earned based on tier and multipliers
        with create_xray_subsegment('calculate_stars'):
            stars_earned = calculate_stars(
                purchase_amount=purchase_data.amount,
                tier=member.tier,
                double_star_day=purchase_data.double_star_day,
                personal_cup=purchase_data.personal_cup
            )
            
            logger.info("Stars calculated for purchase", 
                       member_id=purchase_data.membership_id,
                       tier=member.tier.value,
                       amount=float(purchase_data.amount),
                       stars_earned=stars_earned,
                       double_star_day=purchase_data.double_star_day,
                       personal_cup=purchase_data.personal_cup)
        
        # Update member balance atomically
        now = datetime.utcnow()
        with create_xray_subsegment('update_member_balance'):
            start_time = datetime.utcnow()
            db_client.update_member_balance(
                membership_id=purchase_data.membership_id,
                star_delta=stars_earned,
                annual_star_delta=stars_earned,
                last_activity=now
            )
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            log_dynamodb_operation(logger, 'update_item', 'rewards-program', 
                                 {'PK': f'MEMBER#{purchase_data.membership_id}'}, 
                                 success=True, duration_ms=duration_ms)
        
        # Create star ledger entry for Green tier members
        if member.tier == Tier.GREEN:
            with create_xray_subsegment('create_star_ledger_entry'):
                from common.models import StarLedgerEntry
                ledger_entry = StarLedgerEntry(
                    membership_id=purchase_data.membership_id,
                    earned_date=now,
                    star_count=stars_earned,
                    expiration_date=None,  # Will be set by expiration handler based on activity
                    batch_id=str(uuid.uuid4())
                )
                
                start_time = datetime.utcnow()
                db_client.create_star_ledger_entry(ledger_entry)
                duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                log_dynamodb_operation(logger, 'put_item', 'rewards-program', 
                                     {'PK': f'MEMBER#{purchase_data.membership_id}'}, 
                                     success=True, duration_ms=duration_ms)
                
                if sampler.should_log():
                    logger.debug("Star ledger entry created for Green member", 
                                member_id=purchase_data.membership_id,
                                stars_earned=stars_earned)
        
        # Record purchase transaction
        transaction = Transaction(
            transaction_id=event_msg.transaction_id,
            membership_id=purchase_data.membership_id,
            type=TransactionType.PURCHASE,
            timestamp=now,
            stars_earned=stars_earned,
            purchase_amount=purchase_data.amount,
            description=f"Purchase of ${purchase_data.amount:.2f}"
        )
        
        with create_xray_subsegment('record_transaction'):
            start_time = datetime.utcnow()
            db_client.record_transaction(transaction)
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            log_dynamodb_operation(logger, 'put_item', 'rewards-program', 
                                 {'PK': f'MEMBER#{purchase_data.membership_id}'}, 
                                 success=True, duration_ms=duration_ms)
        
        log_event_processing(logger, 'purchase', purchase_data.membership_id, 
                           success=True, stars_earned=stars_earned,
                           amount=float(purchase_data.amount),
                           transaction_id=event_msg.transaction_id)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Purchase processed successfully',
                'membershipId': purchase_data.membership_id,
                'starsEarned': stars_earned,
                'purchaseAmount': str(purchase_data.amount),
                'transactionId': event_msg.transaction_id
            })
        }
        
    except ValidationException as e:
        logger.warning("Purchase validation failed", 
                      error_code=e.code, error_message=e.message, 
                      validation_details=e.details)
        log_event_processing(logger, 'purchase', success=False, 
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
        logger.error("Purchase business logic error", error_message=error_msg)
        log_event_processing(logger, 'purchase', success=False, 
                           error="MEMBER_NOT_FOUND")
        return {
            'statusCode': 422,
            'body': json.dumps(create_error_response(
                ErrorCode.MEMBER_NOT_FOUND,
                error_msg
            ))
        }
    except Exception as e:
        logger.error("Unexpected purchase error", 
                    exception_type=type(e).__name__, 
                    exception_message=str(e))
        log_event_processing(logger, 'purchase', success=False, 
                           error="INTERNAL_ERROR")
        return {
            'statusCode': 500,
            'body': json.dumps(create_error_response(
                ErrorCode.INTERNAL_ERROR,
                'An unexpected error occurred processing the purchase'
            ))
        }
