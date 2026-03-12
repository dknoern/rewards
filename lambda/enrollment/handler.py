"""Lambda handler for member enrollment events."""

import json
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict

from common.dynamodb import DynamoDBClient
from common.models import MemberProfile, Tier
from common.validation import (
    validate_event_message,
    validate_signup_data,
    create_error_response,
    ValidationException
)
from common.logger import (
    with_structured_logging,
    log_event_processing,
    log_dynamodb_operation,
    create_xray_subsegment,
    StructuredLogger
)


@with_structured_logging('enrollment')
def handler(event: Dict[str, Any], context: Any, logger: StructuredLogger) -> Dict[str, Any]:
    """
    Handle member enrollment events.
    
    Args:
        event: EventBridge event containing signup data
        context: Lambda context object
        logger: Structured logger instance
        
    Returns:
        Response dictionary with status and membership ID or error
    """
    db_client = DynamoDBClient()
    
    try:
        # Extract event data from EventBridge event structure
        if 'detail' in event:
            # This is an EventBridge event
            event_data = event['detail']
            logger.info("Processing EventBridge enrollment event", 
                       source=event.get('source'), 
                       detail_type=event.get('detail-type'))
        else:
            # This is a direct event (for testing)
            event_data = event
            logger.info("Processing direct enrollment event")
            
        # Validate event message structure
        with create_xray_subsegment('validate_event_message'):
            event_msg = validate_event_message(event_data)
            logger.debug("Event message validation successful", 
                        transaction_id=event_msg.transaction_id)
        
        # Check for idempotency
        with create_xray_subsegment('check_idempotency'):
            existing_txn = db_client.check_transaction_exists(event_msg.transaction_id)
            if existing_txn:
                logger.info("Idempotent enrollment request detected", 
                           transaction_id=event_msg.transaction_id,
                           existing_member_id=existing_txn.get('membershipId'))
                log_event_processing(logger, 'enrollment', 
                                   existing_txn.get('membershipId'), 
                                   success=True, idempotent=True)
                return {
                    'statusCode': 200,
                    'body': json.dumps({
                        'message': 'Member already enrolled (idempotent)',
                        'membershipId': existing_txn.get('membershipId'),
                        'transactionId': event_msg.transaction_id
                    })
                }
        
        # Validate signup data
        with create_xray_subsegment('validate_signup_data'):
            signup_data = validate_signup_data(event_msg.data)
            logger.debug("Signup data validation successful", 
                        email_domain=signup_data.email.split('@')[1] if '@' in signup_data.email else 'unknown')
        
        # Generate unique membership ID
        membership_id = str(uuid.uuid4())
        logger.info("Generated new membership ID", membership_id_prefix=membership_id[:8])
        
        # Create member profile
        now = datetime.utcnow()
        profile = MemberProfile(
            membership_id=membership_id,
            email=signup_data.email,
            name=signup_data.name,
            phone=signup_data.phone,
            tier=Tier.GREEN,
            star_balance=0,
            annual_star_count=0,
            enrollment_date=now,
            tier_since=now,
            next_tier_evaluation=now + timedelta(days=365)
        )
        
        # Save to database
        with create_xray_subsegment('create_member_profile'):
            start_time = datetime.utcnow()
            db_client.create_member(profile)
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            log_dynamodb_operation(logger, 'put_item', 'rewards-program', 
                                 {'PK': f'MEMBER#{membership_id}'}, 
                                 success=True, duration_ms=duration_ms)
        
        # Record transaction for idempotency
        from common.models import Transaction, TransactionType
        transaction = Transaction(
            transaction_id=event_msg.transaction_id,
            membership_id=membership_id,
            type=TransactionType.TIER_CHANGE,
            timestamp=now,
            description=f"Member enrolled with {Tier.GREEN.value} tier"
        )
        
        with create_xray_subsegment('record_transaction'):
            start_time = datetime.utcnow()
            db_client.record_transaction(transaction)
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            log_dynamodb_operation(logger, 'put_item', 'rewards-program', 
                                 {'PK': f'MEMBER#{membership_id}'}, 
                                 success=True, duration_ms=duration_ms)
        
        log_event_processing(logger, 'enrollment', membership_id, success=True,
                           tier=Tier.GREEN.value, transaction_id=event_msg.transaction_id)
        
        return {
            'statusCode': 201,
            'body': json.dumps({
                'message': 'Member enrolled successfully',
                'membershipId': membership_id,
                'tier': Tier.GREEN.value,
                'transactionId': event_msg.transaction_id
            })
        }
        
    except ValidationException as e:
        logger.warning("Enrollment validation failed", 
                      error_code=e.code, error_message=e.message, 
                      validation_details=e.details)
        log_event_processing(logger, 'enrollment', success=False, 
                           error=f"{e.code}: {e.message}")
        return {
            'statusCode': 400,
            'body': json.dumps(create_error_response(
                e.code,  # Use the specific error code from the exception
                e.message,
                e.details
            ))
        }
    except ValueError as e:
        # Duplicate enrollment - member already exists
        error_msg = str(e)
        if "already exists" in error_msg:
            logger.warning("Duplicate enrollment attempt", error_message=error_msg)
            log_event_processing(logger, 'enrollment', success=False, 
                               error="DUPLICATE_ENROLLMENT")
            return {
                'statusCode': 422,
                'body': json.dumps(create_error_response(
                    'DUPLICATE_ENROLLMENT',
                    error_msg,
                    {'membershipId': membership_id}
                ))
            }
        # Other ValueError
        logger.error("Enrollment validation error", error_message=error_msg)
        log_event_processing(logger, 'enrollment', success=False, 
                           error="VALIDATION_ERROR")
        return {
            'statusCode': 400,
            'body': json.dumps(create_error_response(
                'VALIDATION_ERROR',
                error_msg
            ))
        }
    except Exception as e:
        logger.error("Unexpected enrollment error", 
                    exception_type=type(e).__name__, 
                    exception_message=str(e))
        log_event_processing(logger, 'enrollment', success=False, 
                           error="INTERNAL_ERROR")
        return {
            'statusCode': 500,
            'body': json.dumps(create_error_response(
                'INTERNAL_ERROR',
                'An unexpected error occurred'
            ))
        }
