"""Lambda handler for star expiration scheduled events."""

import json
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List
from common.dynamodb import DynamoDBClient
from common.models import Tier, Transaction, TransactionType, StarLedgerEntry
from common.logger import (
    with_structured_logging,
    log_event_processing,
    log_dynamodb_operation,
    create_xray_subsegment,
    StructuredLogger
)


@with_structured_logging('expiration')
def handler(event: Dict[str, Any], context: Any, logger: StructuredLogger) -> Dict[str, Any]:
    """
    Handle scheduled star expiration events for Green tier members.

    This handler runs daily at 01:00 UTC to process star expiration for Green tier members.
    Stars expire after 6 months without monthly qualifying activity.

    Args:
        event: EventBridge scheduled event
        context: Lambda context object
        logger: Structured logger instance

    Returns:
        Response dictionary with expiration results
    """
    try:
        current_time = datetime.utcnow()
        logger.info("Star expiration handler started", 
                   execution_time=current_time.isoformat(),
                   event_source=event.get('source', 'unknown'))

        # Initialize DynamoDB client
        db_client = DynamoDBClient()
        
        # Process expiration for Green tier members
        with create_xray_subsegment('process_star_expiration'):
            expiration_results = process_star_expiration(db_client, current_time, logger)

        logger.info("Star expiration processing completed", 
                   **expiration_results)

        log_event_processing(logger, 'star_expiration', success=True, 
                           **expiration_results)

        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Star expiration handler executed successfully',
                'timestamp': current_time.isoformat(),
                'results': expiration_results
            })
        }

    except Exception as e:
        logger.error("Fatal star expiration error", 
                    exception_type=type(e).__name__,
                    exception_message=str(e))
        log_event_processing(logger, 'star_expiration', success=False, 
                           error="FATAL_ERROR")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': 'Internal server error during star expiration',
                'message': str(e),
                'timestamp': datetime.utcnow().isoformat()
            })
        }


def process_star_expiration(
    db_client: DynamoDBClient,
    current_time: datetime,
    logger: StructuredLogger
) -> Dict[str, Any]:
    """
    Process star expiration for all Green tier members.
    
    Args:
        db_client: DynamoDB client instance
        current_time: Current timestamp for expiration calculations
        logger: Structured logger instance
        
    Returns:
        Dictionary with expiration processing results
    """
    members_processed = 0
    members_with_expiration = 0
    total_stars_expired = 0
    
    try:
        # Query all Green tier members using GSI1
        with create_xray_subsegment('query_green_members'):
            start_time = datetime.utcnow()
            green_members = db_client.query_members_by_tier(Tier.GREEN)
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            
            log_dynamodb_operation(logger, 'query', 'rewards-program', 
                                 {'GSI1PK': 'TIER#GREEN'}, 
                                 success=True, duration_ms=duration_ms)
            
            logger.info("Green tier members queried for expiration", 
                       member_count=len(green_members))
        
        for member in green_members:
            members_processed += 1
            logger.debug("Processing member for star expiration", 
                        member_id=member.membership_id,
                        last_activity=member.last_qualifying_activity.isoformat() if member.last_qualifying_activity else None)
            
            # Check if member has qualifying activity in the past month
            one_month_ago = current_time - timedelta(days=30)
            
            if (member.last_qualifying_activity and 
                member.last_qualifying_activity >= one_month_ago):
                # Member has recent activity, no expiration needed
                logger.debug("Member has recent activity, skipping expiration", 
                            member_id=member.membership_id,
                            last_activity=member.last_qualifying_activity.isoformat())
                continue
            
            # Member has no activity in past month, check for expired stars
            with create_xray_subsegment('process_member_expiration'):
                expired_stars = process_member_expiration(
                    db_client, member.membership_id, current_time, logger
                )
            
            if expired_stars > 0:
                members_with_expiration += 1
                total_stars_expired += expired_stars
                logger.info("Stars expired for inactive member", 
                           member_id=member.membership_id,
                           expired_stars=expired_stars)
        
        logger.info("Star expiration batch processing completed", 
                   members_processed=members_processed,
                   members_with_expiration=members_with_expiration,
                   total_stars_expired=total_stars_expired)
        
        return {
            'membersProcessed': members_processed,
            'membersWithExpiration': members_with_expiration,
            'totalStarsExpired': total_stars_expired
        }
        
    except Exception as e:
        logger.error("Star expiration processing failed", 
                    exception_type=type(e).__name__,
                    exception_message=str(e))
        raise


def process_member_expiration(
    db_client: DynamoDBClient,
    membership_id: str,
    current_time: datetime,
    logger: StructuredLogger
) -> int:
    """
    Process star expiration for a specific Green tier member.
    
    Args:
        db_client: DynamoDB client instance
        membership_id: Member to process
        current_time: Current timestamp for expiration calculations
        logger: Structured logger instance
        
    Returns:
        Number of stars expired for this member
    """
    try:
        # Get all star ledger entries for this member
        start_time = datetime.utcnow()
        star_entries = db_client.get_star_ledger_entries(membership_id)
        duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        log_dynamodb_operation(logger, 'query', 'rewards-program', 
                             {'PK': f'MEMBER#{membership_id}'}, 
                             success=True, duration_ms=duration_ms)
        
        if not star_entries:
            logger.debug("No star ledger entries found for member", 
                        member_id=membership_id)
            return 0
        
        # Find entries older than 6 months (6 months = 180 days)
        six_months_ago = current_time - timedelta(days=180)
        expired_entries = []
        total_expired_stars = 0
        
        for entry in star_entries:
            if entry.earned_date <= six_months_ago:
                expired_entries.append(entry)
                total_expired_stars += entry.star_count
                logger.debug("Found expired star entry", 
                            member_id=membership_id,
                            batch_id=entry.batch_id,
                            star_count=entry.star_count,
                            earned_date=entry.earned_date.isoformat())
        
        if not expired_entries:
            logger.debug("No expired stars found for member", 
                        member_id=membership_id,
                        total_entries=len(star_entries))
            return 0
        
        # Expire the stars atomically
        expire_member_stars(
            db_client, membership_id, expired_entries, total_expired_stars, current_time, logger
        )
        
        logger.info("Member star expiration processed", 
                   member_id=membership_id,
                   expired_entries=len(expired_entries),
                   total_expired_stars=total_expired_stars)
        
        return total_expired_stars
        
    except Exception as e:
        logger.error("Member star expiration failed", 
                    member_id=membership_id,
                    exception_type=type(e).__name__,
                    exception_message=str(e))
        raise


def expire_member_stars(
    db_client: DynamoDBClient,
    membership_id: str,
    expired_entries: List[StarLedgerEntry],
    total_expired_stars: int,
    current_time: datetime,
    logger: StructuredLogger
) -> None:
    """
    Expire stars for a member by updating balance and deleting ledger entries.
    
    Args:
        db_client: DynamoDB client instance
        membership_id: Member whose stars are expiring
        expired_entries: List of expired star ledger entries
        total_expired_stars: Total number of stars to expire
        current_time: Current timestamp
        logger: Structured logger instance
    """
    try:
        # Deduct expired stars from balance atomically
        # Use negative star_delta to reduce balance
        with create_xray_subsegment('update_member_balance'):
            start_time = datetime.utcnow()
            db_client.update_member_balance(
                membership_id=membership_id,
                star_delta=-total_expired_stars,
                annual_star_delta=0  # Expiration doesn't affect annual count
            )
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            log_dynamodb_operation(logger, 'update_item', 'rewards-program', 
                                 {'PK': f'MEMBER#{membership_id}'}, 
                                 success=True, duration_ms=duration_ms)
        
        # Delete expired star ledger entries
        with create_xray_subsegment('delete_star_ledger_entries'):
            batch_ids = [entry.batch_id for entry in expired_entries]
            start_time = datetime.utcnow()
            db_client.delete_star_ledger_entries(membership_id, batch_ids)
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            log_dynamodb_operation(logger, 'batch_delete', 'rewards-program', 
                                 {'PK': f'MEMBER#{membership_id}'}, 
                                 success=True, duration_ms=duration_ms)
        
        # Record expiration transaction
        expiration_transaction = Transaction(
            transaction_id=str(uuid.uuid4()),
            membership_id=membership_id,
            type=TransactionType.EXPIRATION,
            timestamp=current_time,
            stars_redeemed=total_expired_stars,  # Use stars_redeemed for expired stars
            description=f"Star expiration: {total_expired_stars} stars expired after 6 months without activity"
        )
        
        with create_xray_subsegment('record_expiration_transaction'):
            start_time = datetime.utcnow()
            db_client.record_transaction(expiration_transaction)
            duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
            log_dynamodb_operation(logger, 'put_item', 'rewards-program', 
                                 {'PK': f'MEMBER#{membership_id}'}, 
                                 success=True, duration_ms=duration_ms)
        
        logger.info("Member stars expired successfully", 
                   member_id=membership_id,
                   expired_stars=total_expired_stars,
                   expired_entries=len(expired_entries),
                   transaction_id=expiration_transaction.transaction_id)
        
    except Exception as e:
        logger.error("Failed to expire member stars", 
                    member_id=membership_id,
                    total_expired_stars=total_expired_stars,
                    exception_type=type(e).__name__,
                    exception_message=str(e))
        raise
